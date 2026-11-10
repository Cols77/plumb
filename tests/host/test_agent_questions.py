"""SR-362: the agent puts the judge's questions in the owner's terms (``plumb question reword``,
merging those on one principle) and asks every one; a point the owner already answered is the
judge's not to raise again (``judge._answered_before``). The model is scripted."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import (  # noqa: F401
    ASK,
    answer,
    judge_asks,
    judge_jobs,
    logged,
    world,
)
from understand.fakes import engine_standins  # noqa: F401 - the fixture
from understand.test_judge_job import SESSION
from understand.test_judge_questions import answer as judged
from understand.test_judge_questions import asking, written

from plumb.api import open_core
from plumb.understand import cmd_clarify, cmd_question, judge

pytestmark = pytest.mark.sr("SR-362")

OTHER = "Should the faster pages also work offline?"
WORDED = "Should only the public pages get faster?"
SAID = "only the public pages, the others can wait"
SHOWN = [{"label": "Only public pages", "description": "The rest stays as it is."},
         {"label": "Every page", "description": "All pages get faster."}]


def question(repo: Path, *argv: str) -> int:
    return cmd_question.run("question", ["--root", str(repo), "--session", SESSION, *argv])


def reword(repo: Path, *covers: str, text: str = WORDED) -> int:
    return question(repo, "reword", *(a for c in covers for a in ("--covers", c)),
                    "--question", text, "--header", "Pages", "--options", json.dumps(SHOWN))


def events(repo: Path, kind: str) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in open_core(repo).events() if e.kind == kind]


def open_keys(repo: Path) -> list[str]:
    return [str(q["key"]) for q in judge.open_questions(open_core(repo), SESSION)]


# ---- reword ----------------------------------------------------------------------------------


def test_ex1_an_answer_to_the_agents_wording_answers_the_question_it_covers(
        world: Path, hook_input) -> None:  # noqa: F811
    """EX-1: the judge's question asked in the agent's words, no id in them: the owner's answer
    answers the judge's question (``asked`` names it) and the judge reads it again."""
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK) == 0
    answer(world, hook_input, WORDED, "Only public pages", options=SHOWN)
    (entry,) = logged(world)
    assert entry["question"] == WORDED and "SR-" not in entry["question"]
    assert entry["asked"]["keys"] == [judge.question_key(ASK)]
    assert [r["id"] for r in entry["asked"]["records"]] == ["SR-001"]
    assert open_keys(world) == []
    (job,) = judge_jobs(world)
    assert job.inputs["records"] == ["SR-001"]


def test_an_answer_given_before_the_rewording_answers_the_question_it_covers(
        world: Path, hook_input) -> None:  # noqa: F811
    """The agent asked in its own words and registered the wording afterwards: the owner's
    earlier answer is pointed at the judge's question (``answer-bound``, their words not
    copied), so it is not asked twice and the judge reads it again."""
    from plumb.understand import premise

    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, WORDED, "Only public pages", options=SHOWN)
    assert open_keys(world) == [judge.question_key(ASK)]
    assert reword(world, ASK) == 0
    (said,) = [e for e in open_core(world).events() if e.kind == "question-answer"]
    (bound,) = events(world, "answer-bound")
    assert bound["answer"] == said.digest and bound["asked"]["keys"] == [judge.question_key(ASK)]
    assert open_keys(world) == []
    core = open_core(world)
    assert [e.digest for e in premise.answer_entries(core, core.index()["SR-001"])] == [said.digest]
    assert [j.inputs["answered"] for j in judge_jobs(world)] == [[said.digest]]
    assert reword(world, ASK) == 1                       # answered: nothing left to word
    assert len(events(world, "answer-bound")) == 1


def test_one_wording_merges_two_questions_and_one_answer_settles_both(
        world: Path, hook_input) -> None:  # noqa: F811
    """Two judge questions hinging on one principle, merged in one wording (named by the start
    of each, comma-separated): one answer answers both, ``asked.keys`` naming each."""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    assert reword(world, "should every page,should the faster pages") == 0
    answer(world, hook_input, WORDED, "Every page", options=SHOWN)
    (entry,) = logged(world)
    assert entry["asked"]["keys"] == [judge.question_key(ASK), judge.question_key(OTHER)]
    assert {r["id"] for r in entry["asked"]["records"]} == {"SR-001", "INT-001"}
    assert open_keys(world) == []
    (job,) = judge_jobs(world)
    assert set(job.inputs["records"]) == {"SR-001", "INT-001"}


FLAG_SHOWN = [{"label": "The change was needed (Recommended)", "description": "the flags go"},
              {"label": "Not sure: restore the original check", "description": "they stay"}]
FLAGGED = "Were the changes to the tests that failed needed, or made just to pass?"
FLAGS = [("tests/test_a.py::test_one", ["SR-001"]),
         ("tests/test_b.py::test_two[x y]", ["SR-001", "SR-002"])]


def _reword_flags(repo: Path, *covers: str) -> int:
    return question(repo, "reword", *(a for c in covers for a in ("--covers", c)),
                    "--question", FLAGGED, "--header", "Changed tests",
                    "--options", json.dumps(FLAG_SHOWN))


def _needed(repo: Path) -> list[bool]:
    from plumb.understand import testchange

    answers = judge.answers_by_key(open_core(repo))
    return [testchange.owner_needed(answers, node, srs) for node, srs in FLAGS]


def test_one_wording_merges_two_flag_questions_and_one_answer_ends_both(
        world: Path, hook_input) -> None:  # noqa: F811
    """report-5f6565d7: the merge check's hidden-regression flag questions are in no session's
    question file; a wording may cover them all the same, and the owner's one "needed" ends
    every flag it covers (``testchange.owner_needed`` reads it by each flag's key)."""
    from plumb.understand import testchange

    texts = [testchange.flag_question(node, srs) for node, srs in FLAGS]
    assert _reword_flags(world, *texts) == 0
    (worded,) = judge.reworded(world, SESSION)
    assert worded["covers"] == [judge.question_key(t) for t in texts]
    assert _needed(world) == [False, False]
    answer(world, hook_input, FLAGGED, FLAG_SHOWN[0]["label"], options=FLAG_SHOWN)
    (entry,) = logged(world)
    assert entry["asked"]["keys"] == worded["covers"] and entry["asked"]["records"] == []
    assert _needed(world) == [True, True]
    assert judge_jobs(world) == []                       # no record goes back to the judge
    answer(world, hook_input, FLAGGED, FLAG_SHOWN[1]["label"], options=FLAG_SHOWN)
    assert _needed(world) == [False, False]              # asked again: the later answer stands


def test_a_flag_answer_given_before_the_rewording_ends_the_flags_it_covers(
        world: Path, hook_input) -> None:  # noqa: F811
    from plumb.understand import testchange

    texts = [testchange.flag_question(node, srs) for node, srs in FLAGS]
    answer(world, hook_input, FLAGGED, FLAG_SHOWN[0]["label"], options=FLAG_SHOWN)
    assert _needed(world) == [False, False]
    assert _reword_flags(world, *texts) == 0 and _reword_flags(world, *texts) == 0
    (bound,) = events(world, "answer-bound")
    assert bound["asked"]["keys"] == [judge.question_key(t) for t in texts]
    assert _needed(world) == [True, True]


def test_a_wording_covering_a_flag_and_a_judge_question_answers_both(
        world: Path, hook_input) -> None:  # noqa: F811
    from plumb.understand import testchange

    flag = testchange.flag_question(*FLAGS[0])
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK, flag) == 0
    answer(world, hook_input, WORDED, "Every page", options=SHOWN)
    (entry,) = logged(world)
    assert entry["asked"]["keys"] == [judge.question_key(ASK), judge.question_key(flag)]
    assert open_keys(world) == []
    assert reword(world, "a flag nobody raised, or made just to pass?") == 1


def test_a_wording_with_a_record_id_or_naming_no_open_question_is_refused(
        world: Path) -> None:  # noqa: F811
    """EX-1: the owner never sees an id; a key naming no open question records nothing."""
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK, text="Should SR-001 cover only public pages?") == 2
    assert reword(world, "a question nobody asked") == 1
    assert judge.reworded(world, SESSION) == []


def test_the_missed_check_counts_a_registered_wording_as_matched(
        world: Path, hook_input) -> None:  # noqa: F811
    """SR-212's check: the last answer, to a wording the agent registered, is no question of
    its own, even when the question it covered left meanwhile (the judge dropped it)."""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    assert reword(world, OTHER, text="Should they work offline?") == 0
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, "Should they work offline?", "Only public pages", options=SHOWN)
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert outcome.state == "ask"
    assert outcome.lines == [cmd_clarify.ASK_QUESTIONS.format(n=1)]


def test_ex5_each_question_carries_its_key_and_plumbs_words_are_marked_to_reword(
        world: Path) -> None:  # noqa: F811
    """EX-5: the agent gets the key ``reword`` takes; a question in plumb's own
    words is marked to be put in the owner's terms first."""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    path = judge.questions_path(world, SESSION)
    raw = json.loads(path.read_text("utf-8"))
    raw[1]["reword"] = True
    path.write_text(json.dumps(raw), "utf-8")
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert {q["key"] for q in outcome.questions} == set(open_keys(world))
    assert [q["reword"] for q in outcome.questions if q["key"] == judge.question_key(OTHER)] \
        == [True]
    assert outcome.lines[1] == cmd_clarify.REWORD_FIRST.format(n=1)


# ---- the judge does not raise an answered point again ---------------------------------------


def _judge_raises(repo: Path, text: str, principle: str, reading: str = "") -> None:
    """The judge raises ``text`` on ``principle``; ``reading``: the round reads that answer."""
    from plumb.understand import judge as judging

    core = open_core(repo)
    job = judging.build(core, SESSION, records=["SR-001"])
    if reading:
        job = dataclasses.replace(job, inputs={**job.inputs, "answered": [reading]})
    judging.apply(core, job, judged(("SR-001", "beyond"), questions=[
        asking("SR-001", question=text, principle=principle)]))


def test_ex2_the_same_point_in_new_words_is_not_asked_again(
        world: Path, hook_input) -> None:  # noqa: F811
    """EX-2: the owner picked an option; the judge raises the same principle about the same
    record in new words, in any later round: it is set aside as answered, not asked."""
    _judge_raises(world, "Should every page load faster, or only the public ones?", "pages")
    (first,) = written(world)
    answer(world, hook_input, first["question"], "Every page", options=first["options"])
    assert logged(world)[0]["asked"]["principle"] == "pages"
    _judge_raises(world, "Which pages should get faster?", "Pages")
    assert [q["question"] for q in written(world)] == []


def test_ex7_an_open_answer_is_not_asked_right_back_but_may_come_back_later(
        world: Path, hook_input) -> None:  # noqa: F811
    """EX-7: 'I don't know' leaves the point open: the round reading it does not ask it again;
    a later round may."""
    _judge_raises(world, "Should every page load faster, or only the public ones?", "pages")
    (first,) = written(world)
    answer(world, hook_input, first["question"], "I don't know, ask the others",
           options=first["options"])
    (said,) = [e for e in open_core(world).events() if e.kind == "question-answer"]
    _judge_raises(world, "Which pages should get faster?", "pages", reading=said.digest)
    assert written(world) == []
    _judge_raises(world, "Which pages should get faster?", "pages")
    assert [q["question"].splitlines()[0] for q in written(world)] == [
        "Which pages should get faster?"]


def test_ex4_a_question_on_another_principle_is_still_asked(
        world: Path, hook_input) -> None:  # noqa: F811
    """EX-4: an answer settles its own principle only."""
    _judge_raises(world, "Should every page load faster, or only the public ones?", "pages")
    (first,) = written(world)
    answer(world, hook_input, first["question"], "Every page", options=first["options"])
    _judge_raises(world, "Should the faster pages also work offline?", "offline")
    assert [q["principle"] for q in written(world)] == ["offline"]


def test_ex3_the_agent_cannot_drop_or_send_back_a_question(
        world: Path) -> None:  # noqa: F811
    """EX-3: one the agent finds obvious is asked all the same: rewording drops nothing, and
    there is no command to send it back."""
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK) == 0
    with pytest.raises(SystemExit):
        question(world, "pushback", "should every page", "--reason", "obvious")
    assert open_keys(world) == [judge.question_key(ASK)]
