"""SR-211 EX-10 and SR-214 EX-2: a merge conflict reaches the owner as one question with both
versions and the keep-this, keep-the-other and both options; a typed reply that answers an open
question and adds a request answers the question and confirms nothing else."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from understand.fakes import as_worker
from understand.test_read_apply import approvals, entries_of, write_applied
from understand.test_read_job import SESSION, log_prompt, make_core, record_text

from iaso.api import open_core
from iaso.understand import conflict_items, judge, read

ASKED = "What should happen when the board is full?"


@pytest.mark.sr("SR-211")
def test_ex10_a_conflict_is_one_question_with_keep_this_keep_the_other_and_both() -> None:
    conflict = SimpleNamespace(labels=("main", "feat-x"), proposed=False, ic="IC-1")
    item = conflict_items.item(conflict)
    assert item["kind"] == "conflict" and "main" in item["text"] and "feat-x" in item["text"]
    assert [(c["label"]) for c in item["choices"]] == ["Keep this one", "Keep the other", "Both"]
    assert "main's version" in item["choices"][0]["consequence"]
    assert "feat-x's version" in item["choices"][1]["consequence"]
    conflict.proposed = True                          # a combined version is already proposed
    assert [c["label"] for c in conflict_items.item(conflict)["choices"]][0] == "Both"


@pytest.mark.sr("SR-214")
def test_ex2_an_answer_plus_a_new_request_answers_only_the_question(repo, write_record) -> None:
    core = make_core(repo, write_record, [record_text(2, "Full board"), record_text(3)])
    judge.add_question(core, SESSION, {
        "key": judge.question_key(ASKED), "job": "judge-x",
        "records": [{"id": "SR-002", "hash": core.index()["SR-002"].hash}],
        "principle": "", "blocking": False, "diagram": False, "reword": False,
        "question": ASKED, "header": "Full board",
        "options": [{"label": "End the program (Recommended)", "description": "It stops."},
                    {"label": "Print draw and start a new game", "description": "Play on."}]})
    said = "2, and also make the pane resizable"
    job = read.build(core, SESSION, message={"digest": log_prompt(core, said), "text": said})
    (item,) = [c for c in job.inputs["questions"] if c["kind"] == "judge"]
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [
            {"id": item["id"], "hash": "", "answer": "change",
             "option": "Print draw and start a new game", "change": None,
             "evidence": "2", "confidence": 0.95},
            {"id": "SR-003", "hash": "", "answer": "open",
             "evidence": "make the pane resizable", "confidence": 0.9}]})
    write_applied(core, applied)
    after = open_core(core.root)
    assert judge.open_questions(after, SESSION) == []          # the question is answered
    assert [e.payload["answer"] for e in entries_of(after, "read-entry")] == ["change", "open"]
    assert approvals(after) == {}                              # the new request confirms nothing
