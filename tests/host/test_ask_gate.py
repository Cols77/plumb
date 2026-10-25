"""SR-361 EX-6: the ask gate. While judge questions wait unasked, edits and writing commands
are refused until the agent asks them through the question tool; reads and the agent's
rewording stay open; it opens once asked, and never closes where the question tool is missing."""

from __future__ import annotations

from pathlib import Path

import pytest
from host.test_answer_rejudge import ASK, judge_asks, world  # noqa: F401
from understand.test_judge_job import SESSION

from plumb.hosts.claude_code import ask_gate, pretool

pytestmark = pytest.mark.sr("SR-361")

OTHER = "Should the faster pages also work offline?"
MAIN = {"session_id": SESSION}


@pytest.fixture(autouse=True)
def attended(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")


def call(repo: Path, tool: str, data: dict | None = None, **tool_input: str) -> str:
    """The deny reason the pre-tool hook gives, or "" when it allows the call."""
    answer = pretool.decide(repo, SESSION, tool, tool_input, data or MAIN)
    return answer.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def test_ex6_open_questions_close_edits_and_writing_commands(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    reason = call(world, "Edit", file_path="src/a.py", old_string="a", new_string="b")
    assert reason == ask_gate.REASON.format(n=1, s="", verb="has")
    assert call(world, "Write", file_path="src/b.py", content="x")
    assert call(world, "Bash", command="rm -rf build")
    assert call(world, "Bash", command="git commit -m wip")
    assert call(world, "Bash", command="echo x > notes.txt")


def test_reads_stay_open(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    assert call(world, "Read", file_path="src/a.py") == ""
    assert call(world, "Grep", pattern="def ") == ""
    for command in ("cat src/a.py | grep def", "git diff main --stat", "ls 2>&1 | head",
                    "plumb show SR-001", ".venv/Scripts/python.exe -m plumb clarify --wait --json"):
        assert call(world, "Bash", command=command) == "", command


def test_rewording_and_pushing_back_stay_open(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    assert call(world, "Bash", command="plumb question reword --covers k --question 'Q?' "
                                        "--header H --options '[]'") == ""
    assert call(world, "Bash", command="plumb question pushback k --reason 'you said so'") == ""


def test_asking_opens_it_until_a_new_question_comes(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    assert call(world, "AskUserQuestion", questions="[]") == ""     # the tool is never refused
    assert call(world, "Edit", file_path="src/a.py", old_string="a", new_string="b") == ""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    assert call(world, "Edit", file_path="src/a.py", old_string="a", new_string="b") == \
        ask_gate.REASON.format(n=1, s="", verb="has")


def test_it_never_closes_without_the_question_tool(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    edit = {"file_path": "src/a.py", "old_string": "a", "new_string": "b"}
    assert call(world, "Edit", {**MAIN, "agent_id": "a1"}, **edit) == ""      # a subagent
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED")                        # headless
    assert call(world, "Edit", **edit) == ""


def test_no_questions_no_gate(world: Path) -> None:  # noqa: F811
    assert call(world, "Edit", file_path="src/a.py", old_string="a", new_string="b") == ""
