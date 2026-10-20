"""SR-334: the questions waiting for the owner are asked by principle, at most three per turn,
a blocking one at once; an answer to a principle reaches every record of its questions, and
the turn-end line counts what still waits. The worker's open questions file is written as the
judge job writes it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import answer as owner_answers

from plumb.api import open_core
from plumb.understand import cmd_clarify, files, judge, premise, summary
from understand.test_judge_cascade import configure, fast_track_on, world  # noqa: F401
from understand.test_judge_job import SESSION
from understand.test_judge_questions import answer, applied_on, asking, written

pytestmark = pytest.mark.sr("SR-334")


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


def backlog(blocking: str = "") -> list[tuple[str, str, bool, tuple[str, ...]]]:
    """62 questions, 50 of them on four principles, the 12 others each its own; ``blocking``:
    one more, blocking the task."""
    sizes = {"public pages only": 20, "one log": 15, "no cache": 10, "plain names": 5}
    out = [(f"Q{p} {n}?", p, False, ("SR-001",)) for p, size in sizes.items()
           for n in range(size)]
    out += [(f"Lone {n}?", "", False, ("SR-001",)) for n in range(12)]
    return out + ([(blocking, "export format", True, ("SR-001",))] if blocking else [])


def asked(outcome: Any) -> list[str]:
    return [q["question"] for q in outcome.questions]


def test_the_judge_names_the_principle_and_whether_it_blocks(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    applied_on(world, ["SR-001"], answer(("SR-001", "supported"), questions=[
        asking("SR-001", principle=" Public  Pages ", blocking=True)]))
    (question,) = written(world)
    assert (question["principle"], question["blocking"]) == ("public pages", True)


def test_ex1_three_principles_asked_and_the_turn_end_line_counts_the_rest(
        world: Path) -> None:  # noqa: F811
    waiting(world, *backlog())
    first = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert first.state == "ask"
    assert asked(first) == ["Qpublic pages only 0?", "Qone log 0?", "Qno cache 0?"]
    assert first.lines == [cmd_clarify.ASK_QUESTIONS.format(n=3)]
    answered_this_turn(world, first.questions)
    assert cmd_clarify.wait(open_core(world), SESSION, timeout=10).state == "ready"
    assert summary.owner_line(open_core(world), SESSION, set()) == "plumb: 59 questions for you"


def test_dec297_the_turn_end_line_counts_waiting_questions_only_when_the_count_changes(
        world: Path) -> None:  # noqa: F811
    """DEC-297 (the owner: "Only when the count changes"): a quiet turn with old waiting
    questions shows nothing; a turn that answers one says how many now wait."""
    waiting(world, *backlog())
    assert summary.owner_line(open_core(world), SESSION, set()) == "plumb: 62 questions for you"
    assert summary.owner_line(open_core(world), SESSION, set()) == ""        # a quiet turn
    answered_this_turn(world, [{"question": "Qno cache 0?"}])
    assert summary.owner_line(open_core(world), SESSION, set()) == "plumb: 61 questions for you"
    assert summary.owner_line(open_core(world), SESSION, set()) == ""


def test_ex2_an_answer_to_a_principle_reaches_every_record_of_its_questions(
        world: Path, hook_input: Any, engine_standins: Any) -> None:  # noqa: F811
    waiting(world, ("Only the public pages?", "public pages only", False, ("INT-001",)),
            ("Leave the admin pages?", "public pages only", False, ("SR-001",)))
    engine_standins.dispatcher.script = {"judge": answer(
        ("INT-001", "supported"), ("SR-001", "supported"), questions=[])}
    (shown,) = cmd_clarify.wait(open_core(world), SESSION, timeout=10).questions
    owner_answers(world, hook_input, shown["question"], "Public pages (Recommended)")
    core = open_core(world)
    index = core.index()
    assert all(premise.answers_of(core, index[i]) for i in ("INT-001", "SR-001"))
    again = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    (job,) = engine_standins.dispatcher.ran("judge")
    assert {r["id"] for r in job.inputs["records"]} == {"INT-001", "SR-001"}
    assert again.state == "ready" and judge.open_questions(open_core(world), SESSION) == []


def test_ex3_a_blocking_question_is_asked_beyond_three(world: Path) -> None:  # noqa: F811
    waiting(world, *backlog("Export to CSV or JSON?"))
    first = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(first)[0] == "Export to CSV or JSON?" and len(first.questions) == 3
    answered_this_turn(world, first.questions[1:] + [{"question": "Qno cache 0?"}])
    again = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(again) == ["Export to CSV or JSON?"]


def test_ex4_mid_task_none_but_a_blocking_one_is_asked(world: Path) -> None:  # noqa: F811
    waiting(world, *backlog())
    mid = cmd_clarify.wait(open_core(world), SESSION, timeout=10, mid_task=True)
    assert mid.state == "ready" and mid.questions == []
    waiting(world, *backlog("Export to CSV or JSON?"))
    mid = cmd_clarify.wait(open_core(world), SESSION, timeout=10, mid_task=True)
    assert asked(mid) == ["Export to CSV or JSON?"]


def test_ex3_two_blocking_questions_on_one_principle_are_both_asked(
        world: Path) -> None:  # noqa: F811
    waiting(world, ("Export to CSV or JSON?", "export format", True, ("SR-001",)),
            ("Export with headers?", "export format", True, ("SR-001",)),
            *backlog())
    first = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert asked(first)[:2] == ["Export to CSV or JSON?", "Export with headers?"]
    mid = cmd_clarify.wait(open_core(world), SESSION, timeout=10, mid_task=True)
    assert asked(mid) == ["Export to CSV or JSON?", "Export with headers?"]
