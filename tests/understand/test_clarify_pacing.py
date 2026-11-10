"""SR-361: every question waiting for the owner is asked as soon as it is raised, one per
principle and every blocking one, with no limit per turn; an answer to a principle reaches
every record of its questions. SR-363: the turn-end line counts no waiting question. The
worker's open questions file is written as the judge job writes it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import answer as owner_answers

from iaso.api import open_core
from iaso.hosts.claude_code.snapshot import awaiting_count
from iaso.understand import cmd_clarify, files, judge, premise, summary, worker
from understand.test_judge_cascade import configure, fast_track_on, world  # noqa: F401
from understand.test_judge_job import SESSION
from understand.test_judge_questions import answer, applied_on, asking, written

pytestmark = pytest.mark.sr("SR-361")


def waiting(repo: Path, *questions: tuple[str, str, bool, tuple[str, ...]]) -> None:
    """The open questions file: ``(question, principle, blocking, record ids)`` each."""
    index = open_core(repo).index()
    files.write_json_atomic(judge.questions_path(repo, SESSION), [
        {"key": judge.question_key(text), "job": "judge-0000000000000000",
         "records": [{"id": i, "hash": index[i].hash} for i in ids], "question": text,
         "header": "Which pages", "principle": principle, "blocking": blocking,
         "options": [{"label": "Public pages (Recommended)", "description": "Only those."},
                     {"label": "Every page", "description": "All of them."}]}
        for text, principle, blocking, ids in questions])


def answered_this_turn(repo: Path, questions: list[dict[str, Any]]) -> None:
    core = open_core(repo)
    for q in questions:
        core.log_append("events", "question-answer", {
            "session": SESSION, "question": q["question"], "answer": "Public pages",
            "via": "question-tool", "asked": {"key": judge.question_key(q["question"])}})


def asked(outcome: Any) -> list[str]:
    return [q["question"] for q in outcome.questions]


def test_the_judge_names_the_principle_and_whether_it_blocks(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    applied_on(world, ["SR-001"], answer(("SR-001", "beyond"), questions=[
        asking("SR-001", principle=" Public  Pages ", blocking=True)]))
    (question,) = written(world)
    assert (question["principle"], question["blocking"]) == ("public pages", True)


def test_ex1_five_questions_raised_mid_task_are_all_asked_at_once(
        world: Path) -> None:  # noqa: F811
    """SR-361 EX-1: three were already answered this turn; the five raised now are all
    asked, none kept for a later turn."""
    waiting(world, *[(f"Earlier {n}?", f"earlier {n}", False, ("SR-001",)) for n in range(3)])
    answered_this_turn(world, [{"question": f"Earlier {n}?"} for n in range(3)])
    five = [(f"Lone {n}?", "", False, ("SR-001",)) for n in range(5)]
    waiting(world, *five)
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert outcome.state == "ask"
    assert sorted(asked(outcome)) == sorted(q for q, *_ in five)
    assert outcome.lines == [cmd_clarify.ASK_QUESTIONS.format(n=5)]


def test_ex2_twelve_questions_eight_on_two_principles_are_six_asked(
        world: Path) -> None:  # noqa: F811
    """SR-361 EX-2: the two principle questions (the bigger first) and the four others."""
    waiting(world, *[(f"Public {n}?", "public pages only", False, ("SR-001",)) for n in range(5)],
            *[(f"Log {n}?", "one log", False, ("SR-001",)) for n in range(3)],
            *[(f"Lone {n}?", "", False, ("SR-001",)) for n in range(4)])
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(outcome)[:2] == ["Public 0?", "Log 0?"]
    assert sorted(asked(outcome)[2:]) == [f"Lone {n}?" for n in range(4)]


def test_ex2_blocking_questions_come_first_even_two_on_one_principle(
        world: Path) -> None:  # noqa: F811
    waiting(world, ("Export to CSV or JSON?", "export format", True, ("SR-001",)),
            ("Export with headers?", "export format", True, ("SR-001",)),
            ("Public 0?", "public pages only", False, ("SR-001",)),
            ("Public 1?", "public pages only", False, ("SR-001",)))
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(outcome) == ["Export to CSV or JSON?", "Export with headers?", "Public 0?"]


def test_ex3_an_answer_to_a_principle_reaches_every_record_of_its_questions(
        world: Path, hook_input: Any, engine_standins: Any) -> None:  # noqa: F811
    """SR-361 EX-3: the questions hinging on the answered principle are settled, not asked."""
    waiting(world, ("Only the public pages?", "public pages only", False, ("INT-001",)),
            ("Leave the admin pages?", "public pages only", False, ("SR-001",)))
    engine_standins.dispatcher.script = {"judge": answer(
        ("INT-001", "supported"), ("SR-001", "supported"), questions=[])}
    (shown,) = cmd_clarify.wait(open_core(world), SESSION, timeout=10).questions
    owner_answers(world, hook_input, shown["question"], "Public pages (Recommended)")
    core = open_core(world)
    index = core.index()
    assert all(premise.answers_of(core, index[i]) for i in ("INT-001", "SR-001"))
    worker.run_once(open_core(world), SESSION)      # the background worker (SR-378)
    again = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    (job,) = engine_standins.dispatcher.ran("judge")
    assert {r["id"] for r in job.inputs["records"]} == {"INT-001", "SR-001"}
    assert again.state == "ready" and judge.open_questions(open_core(world), SESSION) == []


def test_ex4_a_dismissed_question_waits_on_the_band_not_on_the_turn_end_line(
        world: Path) -> None:  # noqa: F811
    """SR-361 EX-4, SR-363 EX-2: the owner dismissed the question (nothing logged): the turn
    end prints no line and the band counts it as waiting."""
    waiting(world, ("Only the public pages?", "public pages only", False, ("SR-001",)))
    cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert summary.owner_line(open_core(world), SESSION) == ""
    assert awaiting_count(open_core(world)) == 1


@pytest.mark.sr("SR-363")
def test_sr363_ex1_questions_raised_and_asked_in_the_turn_are_not_counted(
        world: Path) -> None:  # noqa: F811
    """SR-363 EX-1: three questions raised and asked: no 'questions for you' text."""
    waiting(world, *[(f"Lone {n}?", "", False, ("SR-001",)) for n in range(3)])
    assert len(cmd_clarify.wait(open_core(world), SESSION, timeout=10).questions) == 3
    assert "for you" not in summary.owner_line(open_core(world), SESSION)
    answered_this_turn(world, [{"question": f"Lone {n}?"} for n in range(2)])
    assert "for you" not in summary.owner_line(open_core(world), SESSION)


@pytest.mark.sr("SR-219")
def test_ex3_a_dependent_question_the_answer_does_not_settle_is_asked_on_its_own(
        world: Path, hook_input: Any, engine_standins: Any) -> None:  # noqa: F811
    """SR-219 EX-3: after the principle's answer the judge reads the second record again and
    still asks about it: that question is asked as its own, specific one."""
    waiting(world, ("Only the public pages?", "public pages only", False, ("INT-001",)),
            ("Leave the admin pages?", "public pages only", False, ("SR-001",)))
    engine_standins.dispatcher.script = {"judge": answer(
        ("INT-001", "supported"), ("SR-001", "supported"), questions=[])}
    (shown,) = cmd_clarify.wait(open_core(world), SESSION, timeout=10).questions
    owner_answers(world, hook_input, shown["question"], "Public pages (Recommended)")
    engine_standins.dispatcher.script = {"judge": answer(
        ("INT-001", "supported"), ("SR-001", "beyond"), questions=[
            asking("SR-001", question="Should admins see the public pages' old URLs?")])}
    worker.run_once(open_core(world), SESSION)
    again = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    (text,) = asked(again)
    assert again.state == "ask" and text.startswith("Should admins see the public pages' old")


@pytest.mark.sr("SR-219")
def test_ex8_one_open_question_on_a_principle_is_asked_as_it_is(
        world: Path) -> None:  # noqa: F811
    waiting(world, ("Only the public pages?", "public pages only", False, ("SR-001",)))
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(outcome) == ["Only the public pages?"]


@pytest.mark.sr("SR-219")
def test_ex7_three_records_of_one_principle_are_one_question_naming_them_by_title(
        world: Path) -> None:  # noqa: F811
    """SR-219 EX-7: the judge's principle field groups the questions about the three derived
    records, so one is asked; the agent's wording (``question reword --covers``) names them by
    title, never by id, and covers all three."""
    import json

    from iaso.understand import cmd_question

    waiting(world, *[(f"Records {n}?", "public pages only", False, ("SR-001",))
                     for n in range(3)])
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(outcome) == ["Records 0?"]
    wording = "Should the page speed, the cache and the log all follow public pages only?"
    options = [{"label": "Public pages only", "description": "The three follow it."},
               {"label": "Every page", "description": "The three widen."}]
    covers = [a for n in range(3) for a in ("--covers", f"Records {n}?")]
    assert cmd_question.run("question", ["--root", str(world), "--session", SESSION, "reword",
                                         *covers, "--question", wording, "--header", "Pages",
                                         "--options", json.dumps(options)]) == 0
    (worded,) = judge.reworded(world, SESSION)
    assert len(worded["covers"]) == 3 and "SR-" not in worded["question"]
