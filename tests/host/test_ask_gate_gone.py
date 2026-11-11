"""SR-378 EX-2: an unanswered judge question refuses no edit and no shell command; the question
tool's call is still noted, for the pacing rule (SR-334)."""

from __future__ import annotations

from pathlib import Path

import pytest
from host.test_answer_rejudge import ASK, judge_asks, world  # noqa: F401
from understand.test_judge_job import SESSION

from iaso.hosts.claude_code import pretool
from iaso.understand import judge

pytestmark = pytest.mark.sr("SR-378")

MAIN = {"session_id": SESSION}


def test_ex2_an_open_judge_question_lets_an_unrelated_edit_through(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    judge_asks(world, (ASK, ["SR-001"]))
    edit = {"file_path": "src/other.py", "old_string": "a", "new_string": "b"}
    assert pretool.decide(world, SESSION, "Edit", edit, MAIN) == {}
    assert pretool.decide(world, SESSION, "Bash", {"command": "echo b > src/other.py"},
                          MAIN) == {}
    assert judge.question_key(ASK) not in judge.asked_keys(world, SESSION)
    assert pretool.decide(world, SESSION, "AskUserQuestion", {}, MAIN) == {}
    assert judge.question_key(ASK) in judge.asked_keys(world, SESSION)
