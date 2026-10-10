"""SP8 lane JUDGE, J2: the premise in the committed log (SR-102 EX-7, EX-8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from plumb.api import open_core
from understand.test_judge_job import intent_text, log_prompt, requirement_text

pytestmark = pytest.mark.sr("SR-102")

PROMPT = "please add multiply next to add; 2 times 3 is 6"
DOC = {
    "intent": {"quote": "add multiply next to add", "readback": "Add multiply beside add",
               "will": ["multiply(a, b) returns a * b"], "wont": ["no floats yet"]},
    "requirements": [{"title": "multiply returns the product",
                      "statement": "multiply(a, b) returns a * b",
                      "examples": [{"given": "a = 2 and b = 3", "when": "multiply runs",
                                    "then": "it returns 6", "quote": "2 times 3 is 6"}]}],
}


def _capture(repo: Path, digest: str):
    from plumb.capture.capture import capture

    return capture(open_core(repo), DOC, prompt_digest=digest)


def _premises(repo: Path) -> list:
    return [e for e in open_core(repo).events() if e.kind == "premise"]


def test_ex7_capture_commits_message_text_and_digest(repo: Path) -> None:
    digest = log_prompt(repo, PROMPT)
    result = _capture(repo, digest)
    (entry,) = _premises(repo)
    assert entry.payload["text"] == PROMPT
    assert entry.payload["digest"] == digest
    assert entry.payload["digest"] == "sha256:" + hashlib.sha256(PROMPT.encode()).hexdigest()
    assert entry.payload["session"] == "s1"
    assert entry.payload["used_by"] == list(result.written)


def test_a_second_capture_of_the_same_words_adds_only_what_is_new(repo: Path) -> None:
    from plumb.understand import premise

    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    core = open_core(repo)
    premise.commit(core, DOC, type("R", (), {"written": ("INT-001",), "updated": ()})(),
                   prompt_digest=digest)
    assert len(_premises(repo)) == 1                   # INT-001 was already named
    premise.commit(core, DOC, type("R", (), {"written": (), "updated": ("SR-009",)})(),
                   prompt_digest=digest)
    assert [e.payload["used_by"] for e in _premises(repo)] == [["INT-001", "SR-001"],
                                                               ["SR-009"]]


def test_nothing_is_committed_without_a_message(repo: Path) -> None:
    from plumb.capture.capture import capture

    capture(open_core(repo), DOC)
    assert _premises(repo) == []


def test_ex8_fresh_clone_judges_from_committed_log(repo: Path) -> None:
    from plumb.understand import judge, premise

    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    (repo / ".plumb" / "session" / "prompts.jsonl").unlink()      # a fresh clone: no session log
    core = open_core(repo)
    got = premise.premise_of(core, core.index()["SR-001"])
    assert [m["text"] for m in got.messages] == [PROMPT]
    assert got.on_file
    job = judge.build(core, "s1", records=["INT-001", "SR-001"])
    assert job is not None
    assert all(r["premise"]["messages"][0]["text"] == PROMPT for r in job.inputs["records"])


def test_the_committed_log_is_read_before_the_session_log(repo: Path, write_record) -> None:
    from plumb.understand import premise

    digest = log_prompt(repo, "A")
    write_record(repo, intent_text(1, "A", "Keep one log", prompt=digest))
    core = open_core(repo)
    core.log_append("events", "premise", {"digest": digest, "text": "A (committed copy)",
                                          "session": "s1", "used_by": ["INT-001"]})
    got = premise.premise_of(open_core(repo), open_core(repo).index()["INT-001"])
    assert got.messages[0]["text"] == "A (committed copy)"


def test_a_fragment_premise_says_the_words_are_not_on_file(repo: Path, write_record) -> None:
    from plumb.understand import premise

    write_record(repo, intent_text(1, "a fragment of what was said", "Do the thing"))
    core = open_core(repo)
    got = premise.premise_of(core, core.index()["INT-001"])
    assert not got.on_file and got.messages == ()
    assert got.fragment == "a fragment of what was said"
    given = got.as_input()
    assert given["messages"][0]["partial"] is True
    assert given["messages"][0]["text"] == "a fragment of what was said"


def test_the_stored_question_and_the_parent_are_part_of_a_requirement_premise(
        repo: Path, write_record) -> None:
    from plumb.approvals import approval_items
    from plumb.understand import premise

    digest = log_prompt(repo, "B")
    write_record(repo, intent_text(1, "B", "Two logs", prompt=digest,
                                   question="One log or two? A: one. B: two."))
    write_record(repo, requirement_text(1, "Two logs", "There are two logs", intent=1))
    core = open_core(repo)
    core.log_append("events", "approval", {"records": approval_items(core, ["INT-001"]),
                                           "by": "owner"})
    core = open_core(repo)
    got = premise.premise_of(core, core.index()["SR-001"])
    assert got.question == "One log or two? A: one. B: two."
    assert got.parent == "INT-001"
    assert [m["text"] for m in got.messages] == ["B"]


def test_validate_flags_a_premise_whose_digest_differs(repo: Path) -> None:
    from plumb.understand import premise
    from plumb.validate import validate

    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    assert premise.problems(open_core(repo)) == []
    core = open_core(repo)
    core.log_append("events", "premise", {"digest": "sha256:" + "0" * 64,
                                          "text": "edited words", "session": "s1",
                                          "used_by": ["INT-001"]})
    problems = premise.problems(open_core(repo))
    assert len(problems) == 1 and "digest" in problems[0]
    assert any("digest" in f.message for f in validate(open_core(repo)))


def test_validate_flags_a_settled_record_whose_premise_is_not_committed(repo: Path) -> None:
    from plumb.approvals import approval_items
    from plumb.understand import premise
    from understand.fakes import as_worker

    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    core = open_core(repo)
    payload = {"records": approval_items(core, ["SR-001"]), "by": "settled", "session": "s1",
               "job": "judge-1", "model": "fake", "score": 0.97,
               "premise_digest": "sha256:" + "1" * 64, "calibration": "sha256:2"}
    with as_worker(core.root, "s1"):
        core.log_append("events", "approval", payload)
    (problem,) = premise.problems(open_core(repo))
    assert "SR-001" in problem and "not in the committed log" in problem
    json.dumps(problem)
