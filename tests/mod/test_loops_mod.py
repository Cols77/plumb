"""SR-393: the loops the band counts and its pane lists. ``iaso mod loops`` answers what
``iaso loops --json`` does, with the one change stamp's path, and writes nothing."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from mod.helpers import run_mod

from iaso import cli
from iaso.understand import cmd_intent, loops

pytestmark = pytest.mark.sr("SR-393")


@pytest.fixture(autouse=True)
def seams(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test runs `claude`: no session is running."""
    monkeypatch.setattr(loops, "claude_sessions", lambda: {})


def _files(root: Path) -> dict[str, int]:
    return {p.as_posix(): p.stat().st_mtime_ns for p in root.rglob("*")
            if p.is_file() and ".git/objects" not in p.as_posix()}


def test_mod_loops_answers_the_listing(repo: Path, monkeypatch, capsys) -> None:
    cmd_intent.open_loop(repo, "sess", "sha256:" + "a" * 64)
    before = _files(repo)
    code, answer, _ = run_mod(monkeypatch, capsys, repo, "loops", stdin={})
    assert code == 0 and answer["stamp"].endswith("iaso-loops.stamp")
    assert [r["kind"] for r in answer["rows"]] == ["intent"] and answer["idle"] == 1
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    cli.main(["loops", "--root", str(repo), "--json"])
    assert answer == json.loads(capsys.readouterr().out)
    assert _files(repo) == before
