"""SR-361 EX-6: the ask gate. While judge questions wait unasked, edits and writing commands
are refused until the agent asks them through the question tool; reads and the agent's
rewording stay open; it opens once asked, and never closes where the question tool is missing."""

from __future__ import annotations

import json
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


def test_rewording_stays_open(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    assert call(world, "Bash", command="plumb question reword --covers k --question 'Q?' "
                                        "--header H --options '[]'") == ""


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


def test_the_clarify_it_names_stays_open_in_every_spelling(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    for command in (".venv/Scripts/python.exe -m plumb clarify --wait --json",
                    ".venv\\Scripts\\python.exe -m plumb clarify --wait --json | head -40",
                    "cd C:/coding/plumb && .venv/Scripts/python.exe -m plumb clarify --wait",
                    "uv run plumb clarify --wait --json 2>&1 | tail -5"):
        assert call(world, "Bash", command=command) == "", command
    assert call(world, "Bash", command="cd src && rm a.py")


def test_scratch_files_outside_the_project_stay_writable(
        world: Path, tmp_path_factory: pytest.TempPathFactory) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    scratch = tmp_path_factory.mktemp("scratch") / "options.json"
    assert call(world, "Write", file_path=str(scratch), content="[]") == ""
    assert call(world, "Write", file_path=str(world / "src" / "b.py"), content="x")


def test_a_session_older_than_the_matcher_opens_it_by_asking(
        world: Path, hook_input, tmp_path: Path) -> None:  # noqa: F811
    """hooks.json is read at session start: a session begun before the pre-tool hook covered
    the question tool still opens the gate, by the answer hook or the transcript."""
    from host.test_answer_rejudge import answer

    judge_asks(world, (ASK, ["SR-001"]))
    edit = {"file_path": "src/a.py", "old_string": "a", "new_string": "b"}
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"timestamp": "2020-01-01T00:00:00Z", "message": {
        "content": [{"type": "tool_use", "name": "AskUserQuestion"}]}}) + "\n", "utf-8")
    seen = {**MAIN, "transcript_path": str(transcript)}
    assert call(world, "Edit", seen, **edit)                  # asked before the question came
    with transcript.open("a", encoding="utf-8") as f:         # dismissed: no answer hook
        f.write(json.dumps({"timestamp": "2099-01-01T00:00:00Z", "message": {
            "content": [{"type": "tool_use", "name": "AskUserQuestion"}]}}) + "\n")
    assert call(world, "Edit", seen, **edit) == ""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    answer(world, hook_input, "Something else entirely?", "Every page")   # answered: the hook
    assert call(world, "Edit", **edit) == ""


def test_no_questions_no_gate(world: Path) -> None:  # noqa: F811
    assert call(world, "Edit", file_path="src/a.py", old_string="a", new_string="b") == ""


def test_the_stand_in_question_tool_is_a_question_tool(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """DEC-407: a headless run with the stand-in (no attended flag, the stand-in flag) is
    gated like an attended session; calling the stand-in is never refused and opens the gate."""
    judge_asks(world, (ASK, ["SR-001"]))
    edit = {"file_path": "src/a.py", "old_string": "a", "new_string": "b"}
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED")
    assert call(world, "Edit", **edit) == ""                                   # no tool at all
    monkeypatch.setenv(ask_gate.STAND_IN_ENV, "1")
    assert ask_gate.applies(MAIN) and not ask_gate.applies({**MAIN, "agent_id": "a1"})
    assert call(world, "Edit", **edit)
    assert call(world, ask_gate.STAND_IN_TOOL, questions="[]") == ""
    assert call(world, "Edit", **edit) == ""
