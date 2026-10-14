"""The CLI-only fallback: plumb turn start and plumb turn end (sp4 3.2, SR-053)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from hosts_helpers import make_project

from plumb.cli import main

pytestmark = pytest.mark.sr("SR-053")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    make_project(repo, write_record)
    monkeypatch.chdir(repo)
    return repo


def _prompts(repo: Path) -> list[dict]:
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_turn_start_logs_digest_and_prints_delta(project: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("please make SR-001 handle floats"))
    assert main(["turn", "start", "--session", "s1"]) == 0
    out = capsys.readouterr().out
    assert "SR-001 [proposed] Adds numbers" in out
    [entry] = _prompts(project)
    assert entry["session"] == "s1" and entry["digest"].startswith("sha256:")
    # R13 Q4: the agent recorded this message itself, not a host's prompt hook
    assert entry["via"] == "turn"
    # the session's first turn also gives the brief; the second does not
    monkeypatch.setattr("sys.stdin", io.StringIO("and SR-001 again"))
    assert main(["turn", "start", "--session", "s1"]) == 0
    second = capsys.readouterr().out
    assert "SR-001" not in second  # deduplicated delta (R9)
    assert len(_prompts(project)) == 2


def test_turn_start_reads_prompt_file(project: Path, tmp_path: Path, capsys) -> None:
    prompt = tmp_path / "p.txt"
    prompt.write_text("look at SR-001", encoding="utf-8")
    assert main(["turn", "start", "--session", "s2", "--prompt-file", str(prompt)]) == 0
    assert "SR-001" in capsys.readouterr().out
    assert _prompts(project)[0]["text"] == "look at SR-001"


def test_turn_end_prints_summary_and_block_exit_0(project: Path, monkeypatch,
                                                  capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("change add"))
    assert main(["turn", "start", "--session", "s1"]) == 0
    capsys.readouterr()
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return int(a) + int(b)\n",
                                             "utf-8")
    assert main(["turn", "end", "--session", "s1"]) == 0
    out = capsys.readouterr().out
    assert "is stale and unresolved" in out
    # a second turn end of the same turn never blocks again (no loop)
    assert main(["turn", "end", "--session", "s1", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert data["block"] is None


def test_turn_outside_plumb_repo_is_silent(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("hello"))
    assert main(["turn", "start"]) == 0
    assert capsys.readouterr().out == ""


def test_hook_with_host_and_json_format(project: Path, monkeypatch, capsys) -> None:
    event = {"session_id": "h1", "text": "about SR-001", "cwd": str(project)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert main(["hook", "prompt", "--host", "pi", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert any("SR-001" in line for line in data["agent_context"])
    assert set(data) == {"agent_context", "owner_lines", "block", "status_line"}
    assert _prompts(project)[0]["via"] == "hook"


def test_hook_claude_format_is_codex_wire(project: Path, monkeypatch, capsys) -> None:
    event = {"session_id": "c1", "prompt": "about SR-001", "cwd": str(project),
             "hook_event_name": "UserPromptSubmit", "turn_id": "t"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert main(["hook", "prompt", "--host", "codex", "--format", "claude"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "SR-001" in data["hookSpecificOutput"]["additionalContext"]


def test_notify_reads_last_argument_and_never_blocks(project: Path, monkeypatch,
                                                     capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("change add"))
    assert main(["turn", "start", "--session", "n1"]) == 0
    capsys.readouterr()
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return b + a\n", "utf-8")
    payload = json.dumps({"type": "agent-turn-complete", "thread-id": "n1",
                          "cwd": str(project)})
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["hook", "stop", "--host", "codex", "--format", "text", "--notify",
                 payload]) == 0
    assert "relies on it" not in capsys.readouterr().out
