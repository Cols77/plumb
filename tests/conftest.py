"""Shared fixtures for every lane (spec 12.4): ``repo``, ``write_record``, ``hook_input``."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

_KIND_DIRS = {"INT": "intents", "SR": "requirements", "DEC": "decisions", "FEAT": "features",
              "NC": "ncs"}
_ID_LINE = re.compile(r"^id:\s*['\"]?((?:INT|SR|DEC|FEAT|NC)-\d+)", re.MULTILINE)


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` and return stdout (raises on failure)."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            check=True, encoding="utf-8")
    return result.stdout


@pytest.fixture(autouse=True)
def owner_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test process stands in for the owner's interactive terminal: every owner-only
    question (``approvals.require_owner``) is answered "y". The guard's own tests
    (``tests/core/test_owner_terminal.py``) restore the real terminal check."""
    from plumb import approvals

    monkeypatch.setattr(approvals, "owner_terminal_answer", lambda question: "y")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary git repository adopted by plumb (``.plumb/`` dirs) with one commit."""
    from plumb.commands import init_repo

    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    init_repo(root)
    (root / "README.md").write_text("test repo\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")
    return root


def _write_record(repo: Path, text: str, name: str | None = None) -> Path:
    match = _ID_LINE.search(text)
    if match is None:
        raise ValueError("record text has no id line")
    record_id = match.group(1)
    directory = repo / ".plumb" / _KIND_DIRS[record_id.split("-")[0]]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or f"{record_id}.md")
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.fixture
def write_record() -> Callable[..., Path]:
    """``write_record(repo, text)`` writes a record file into the kind's directory."""
    return _write_record


@pytest.fixture
def hook_input() -> Callable[..., str]:
    """``hook_input(event, **fields)`` returns Claude Code hook stdin JSON."""

    def build(event: str, **fields: object) -> str:
        data: dict[str, object] = {
            "session_id": "test-session",
            "transcript_path": "",
            "cwd": ".",
            "hook_event_name": event,
        }
        data.update(fields)
        return json.dumps(data)

    return build
