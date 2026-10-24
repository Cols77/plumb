"""SR-338 EX-1, EX-4: the SessionEnd hook marks the session's folder ended; a resumed session's
SessionStart unmarks it."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from plumb.hosts.claude_code import session_end, session_start

pytestmark = pytest.mark.sr("SR-338")


def _end(repo: Path, hook_input, session: str = "s1") -> str:
    out = io.StringIO()
    payload = hook_input("SessionEnd", session_id=session, reason="exit")
    assert session_end.main(stdin=io.StringIO(payload), stdout=out, root=repo) == 0
    return out.getvalue()


def test_ex1_the_session_folder_is_marked_ended(repo: Path, hook_input) -> None:
    folder = repo / ".plumb" / "session" / "s1"
    folder.mkdir(parents=True)
    assert _end(repo, hook_input) == ""
    data = json.loads((folder / "ended.json").read_text(encoding="utf-8"))
    assert data["ended"] and data["reason"] == "exit"


def test_a_session_with_no_folder_gets_none(repo: Path, hook_input) -> None:
    assert _end(repo, hook_input, "s2") == ""
    assert not (repo / ".plumb" / "session" / "s2").exists()


def test_ex4_a_resumed_session_is_unmarked(repo: Path, hook_input) -> None:
    folder = repo / ".plumb" / "session" / "s1"
    folder.mkdir(parents=True)
    _end(repo, hook_input)
    payload = hook_input("SessionStart", session_id="s1", source="resume")
    session_start.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo,
                       verify=None)
    assert folder.is_dir() and not (folder / "ended.json").exists()
