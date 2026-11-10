"""The premise: the owner's words come from the session log, never the tracked log (DEC-116)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from iaso.api import open_core
from understand.test_judge_job import intent_text, log_prompt, requirement_text

pytestmark = pytest.mark.sr("SR-239")

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
    from iaso.capture.capture import capture

    return capture(open_core(repo), DOC, prompt_digest=digest)


def _premises(repo: Path) -> list:
    return [e for e in open_core(repo).events() if e.kind == "premise"]


def test_ex7_capture_copies_no_message_text_into_the_tracked_log(repo: Path) -> None:
    """DEC-116: the owner's messages stay out of git."""
    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    assert _premises(repo) == []
    tracked = "".join(p.read_text(encoding="utf-8", errors="ignore")
                      for p in (repo / ".iaso" / "log").rglob("*.json"))
    assert PROMPT not in tracked


def test_ex10_a_record_judged_where_it_was_captured_is_not_judged_again_elsewhere(
        repo: Path) -> None:
    """SR-239 EX-10: a clone without the capturing machine's log reads the record judged;
    its judgment stands, nothing is queued, and no 'missing words' mark exists (DEC-116)."""
    from dataclasses import fields

    from iaso.understand import backlog, judge, premise
    from understand.test_judge_job import approve

    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    core = open_core(repo)
    approve(core, "SR-001")
    (repo / ".iaso" / "session" / "prompts.jsonl").unlink()      # a clone: no session log
    core = open_core(repo)
    got = premise.premise_of(core, core.index()["SR-001"])
    assert got.messages == () and not got.on_file
    assert "missing" not in {f.name for f in fields(got)}
    assert "unavailable" not in got.as_input()
    assert core.status(["SR-001"])["SR-001"].confirmation == "confirmed"
    assert "SR-001" not in backlog.waiting(core, "s1")
    job = judge.build(core, "s1", records=["SR-001"])
    assert job is None or "unavailable" not in job.inputs["records"][0]["premise"]


def test_the_session_log_gives_the_text_of_the_message(repo: Path) -> None:
    from iaso.understand import premise

    digest = log_prompt(repo, PROMPT)
    _capture(repo, digest)
    core = open_core(repo)
    got = premise.premise_of(core, core.index()["SR-001"])
    assert [m["text"] for m in got.messages] == [PROMPT]
    assert got.on_file


def test_an_old_committed_premise_entry_still_serves_a_clone(repo: Path, write_record) -> None:
    from iaso.understand import premise

    digest = log_prompt(repo, "A")
    write_record(repo, intent_text(1, "A", "Keep one log", prompt=digest))
    (repo / ".iaso" / "session" / "prompts.jsonl").unlink()
    core = open_core(repo)
    core.log_append("events", "premise", {"digest": digest, "text": "A", "session": "s1",
                                          "used_by": ["INT-001"]})
    got = premise.premise_of(open_core(repo), open_core(repo).index()["INT-001"])
    assert got.messages[0]["text"] == "A"


def test_the_session_log_is_read_before_an_old_committed_entry(repo: Path, write_record) -> None:
    from iaso.understand import premise

    digest = log_prompt(repo, "A")
    write_record(repo, intent_text(1, "A", "Keep one log", prompt=digest))
    core = open_core(repo)
    core.log_append("events", "premise", {"digest": digest, "text": "A (committed copy)",
                                          "session": "s1", "used_by": ["INT-001"]})
    got = premise.premise_of(open_core(repo), open_core(repo).index()["INT-001"])
    assert got.messages[0]["text"] == "A"


def test_a_fragment_premise_says_the_words_are_not_on_file(repo: Path, write_record) -> None:
    from iaso.understand import premise

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
    from iaso.approvals import approval_items
    from iaso.understand import premise

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
    from iaso.understand import premise
    from iaso.validate import validate

    core = open_core(repo)
    core.log_append("events", "premise", {"digest": "sha256:" + hashlib.sha256(
        PROMPT.encode()).hexdigest(), "text": PROMPT, "session": "s1", "used_by": ["INT-001"]})
    assert premise.problems(open_core(repo)) == []
    core = open_core(repo)
    core.log_append("events", "premise", {"digest": "sha256:" + "0" * 64,
                                          "text": "edited words", "session": "s1",
                                          "used_by": ["INT-001"]})
    problems = premise.problems(open_core(repo))
    assert len(problems) == 1 and "digest" in problems[0]
    assert any("digest" in f.message for f in validate(open_core(repo)))
