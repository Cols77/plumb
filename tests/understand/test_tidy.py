"""SR-162, SR-218: a background job reads the judge's waiting questions against the owner's
logged answers and confirmed records and closes the ones they already answer; the model is
stubbed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.understand import files, tidy, worker
from understand.test_judge_job import SESSION, requirement_text

pytestmark = pytest.mark.sr("SR-217")

SAYS = "A conflict may be answered through the agent in chat"


@pytest.fixture
def world(repo: Path, write_record, engine_standins):
    write_record(repo, requirement_text(1, "Chat answers", SAYS))
    return engine_standins


# -- SR-218: waiting questions (report-ec092f5e: the job read only the retired cards) ----------

ASKED = "Should a merged fix keep its branch?"
ANSWERED = "Does a landing delete the branch of a finished worktree?"
SAID = "remove the worktree but not the branch, remove duplicates"


def _waiting(repo: Path) -> str:
    """A judge question on SR-001 in a session, and the owner's earlier answer logged."""
    from plumb.understand import judge

    index = open_core(repo).index()
    files.write_json_atomic(judge.questions_path(repo, "cli"), [
        {"key": judge.question_key(ASKED), "job": "judge-0000000000000000", "header": "Branch",
         "records": [{"id": "SR-001", "hash": index["SR-001"].hash}], "question": ASKED,
         "options": [{"label": "Keep", "description": ""}, {"label": "Delete", "description": ""}]}])
    (entry,) = open_core(repo).log_append_many("events", [("question-answer", {
        "session": SESSION, "question": ANSWERED, "answer": SAID, "via": "question-tool",
        "options": []})])
    return entry.digest


def _tidy(repo: Path) -> None:
    core = open_core(repo)
    tidy.enqueue(core, SESSION)
    worker.run_once(core, SESSION)


def _left(repo: Path) -> list[str]:
    from plumb.understand import judge

    return [str(q.get("question")) for q in judge.open_anywhere(open_core(repo))]


def _close(world, digest: str, quote: str) -> None:
    from plumb.understand import judge

    world.dispatcher.script = {"tidy": {"questions": [
        {"question": judge.question_key(ASKED), "answer": digest, "quote": quote}]}}


def test_a_waiting_question_the_owners_answer_settles_closes_quoting_it(
        repo: Path, world) -> None:
    digest = _waiting(repo)
    assert _left(repo) == [ASKED]
    _close(world, digest, "remove the worktree but not the branch")
    _tidy(repo)
    assert _left(repo) == []
    (bound,) = [e for e in open_core(repo).events() if e.kind == "answer-bound"]
    assert bound.payload["by"] == "tidy" and bound.payload["answer"] == digest
    assert bound.payload["quote"] == "remove the worktree but not the branch"


def test_a_quote_not_in_the_answer_closes_nothing(repo: Path, world) -> None:
    _close(world, _waiting(repo), "delete the branch")
    _tidy(repo)
    assert _left(repo) == [ASKED]


def test_the_owner_can_reopen_a_closed_question(repo: Path, world, capsys) -> None:
    from plumb.understand import cmd_question

    _close(world, _waiting(repo), "remove the worktree but not the branch")
    _tidy(repo)
    assert _left(repo) == []
    assert cmd_question.run("question", ["--root", str(repo), "--session", SESSION,
                                         "reopen", ASKED[:20]]) == 0
    assert _left(repo) == [ASKED]


def test_the_job_reads_waiting_questions(repo: Path, world) -> None:
    _waiting(repo)
    assert tidy.build(open_core(repo), SESSION) is not None
