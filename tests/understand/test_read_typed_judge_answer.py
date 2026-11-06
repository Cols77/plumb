"""A judge question the owner answers in a typed message (no question tool in the session) is
read as an answer to that question (SR-214: the reader reads the message against the open
questions): the question closes, never asked again as it was, and its records go back to the
judge with the owner's words. The answer is to the question only: no record is taken as
answered, agreed or rejected by it (EX-7 stands). Case eval-c48f4019: the full-board question
kept offering "end the program" after the owner typed "print draw, then a new game"."""

from __future__ import annotations

import pytest
from understand.fakes import as_worker
from understand.test_read_apply import write_applied
from understand.test_read_job import SESSION, log_prompt, make_core, record_text

from plumb.api import open_core
from plumb.understand import jobs, judge, read

pytestmark = pytest.mark.sr("SR-214")

ASKED = "What should happen when the board is full?"
SAID = "On a full board print draw, clear the board and start a new game."


@pytest.fixture
def core(repo, write_record):
    return make_core(repo, write_record, [record_text(2, "Full board"), record_text(3)])


def _ask(core) -> None:
    judge.add_question(core, SESSION, {
        "key": judge.question_key(ASKED), "job": "judge-x",
        "records": [{"id": "SR-002", "hash": core.index()["SR-002"].hash}],
        "principle": "", "blocking": False, "diagram": False, "reword": False,
        "question": ASKED, "header": "Full board",
        "options": [{"label": "End the program (Recommended)", "description": "It stops."},
                    {"label": "Print draw and start a new game", "description": "Play on."}]})


def test_a_typed_answer_to_a_judge_question_closes_it_and_rejudges_its_record(core) -> None:
    _ask(core)
    assert judge.open_questions(open_core(core.root), SESSION)
    digest = log_prompt(core, SAID)
    job = read.build(core, SESSION, message={"digest": digest, "text": SAID})
    assert job is not None, "the open judge question is read against the message"
    assert not job.inputs["shown"], "the question's record was not shown (EX-7)"
    (item,) = [c for c in job.inputs["questions"] if c["kind"] == "judge"]
    assert item["text"] == ASKED and not item["record"]

    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [{
            "id": item["id"], "hash": "", "answer": "change",
            "option": "Print draw and start a new game", "change": None,
            "evidence": "print draw, clear the board and start a new game",
            "confidence": 0.95}]})
    write_applied(core, applied)
    after = open_core(core.root)

    assert judge.open_questions(after, SESSION) == [], "never asked again as it was"
    queued = [j for j in jobs.queued(core.root, SESSION) if j.kind == judge.kind]
    assert [j.inputs["records"] for j in queued] == [["SR-002"]]
    from plumb.understand import premise

    (said,) = premise.answer_entries(after, after.index()["SR-002"])
    assert said.payload["text"] == SAID and said.payload["question"] == ASKED
    # an answer to the question only: nothing approved or rejected on its words
    assert not [e for e in after.events() if e.kind in ("approval", "rejection")]


def test_the_round_reading_a_typed_answer_does_not_ask_the_point_right_back(core) -> None:
    """The judge job the typed answer queues reads the owner's words: the same point raised
    again in that round, recommending what the owner just ruled out, is not asked (SR-362
    EX-2/EX-7 for a typed answer, as for a question-tool one)."""
    import dataclasses

    from understand.test_judge_questions import answer as judged
    from understand.test_judge_questions import asking

    judge.add_question(core, SESSION, {
        "key": judge.question_key(ASKED), "job": "judge-x",
        "records": [{"id": "SR-002", "hash": core.index()["SR-002"].hash}],
        "principle": "full board", "blocking": False, "diagram": False, "reword": False,
        "question": ASKED, "header": "Full board",
        "options": [{"label": "End the program (Recommended)", "description": "It stops."},
                    {"label": "Print draw and start a new game", "description": "Play on."}]})
    digest = log_prompt(core, SAID)
    job = read.build(core, SESSION, message={"digest": digest, "text": SAID})
    (item,) = [c for c in job.inputs["questions"] if c["kind"] == "judge"]
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [{
            "id": item["id"], "hash": "", "answer": "change", "option": None, "change": None,
            "evidence": "print draw, clear the board and start a new game",
            "confidence": 0.95}]})
    write_applied(core, applied)
    after = open_core(core.root)
    (queued,) = [j for j in jobs.queued(core.root, SESSION) if j.kind == judge.kind]
    queued = dataclasses.replace(queued, inputs=judge.recompute(after, queued) or queued.inputs)
    with as_worker(core.root, SESSION):
        judge.apply(after, queued, judged(("SR-002", "supported"), questions=[asking(
            "SR-002", question="When the board fills, should the program end?",
            header="Full board", principle="Full board",
            options=[{"label": "End the program", "consequence": "It stops."},
                     {"label": "Start a new game", "consequence": "Play on."}],
            recommended_reason="a full board ends the game")]))
    assert [q["question"] for q in judge._logged_questions(core.root, SESSION)
            if q["key"] != judge.question_key(ASKED)] == []
    assert judge.open_questions(open_core(core.root), SESSION) == []


def test_an_unclear_typed_answer_leaves_the_judge_question_open(core) -> None:
    _ask(core)
    message = "hmm, either could work"
    digest = log_prompt(core, message)
    job = read.build(core, SESSION, message={"digest": digest, "text": message})
    assert job is not None
    (item,) = [c for c in job.inputs["questions"] if c["kind"] == "judge"]
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [{
            "id": item["id"], "hash": "", "answer": "open", "option": None, "change": None,
            "evidence": message, "confidence": 0.9}]})
    write_applied(core, applied)
    assert [q["key"] for q in judge.open_questions(open_core(core.root), SESSION)] == [
        judge.question_key(ASKED)]
