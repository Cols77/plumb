"""The owner drops an open intent loop they no longer want, so no new session reopens it."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.understand import cmd_intent, gate

pytestmark = pytest.mark.sr("SR-447")

OLD, NEW = "sa", "sb"
DIGEST = "sha256:" + "b" * 64


def _drop(repo: Path, *argv: str) -> int:
    return cmd_intent.run("intent", ["drop", *argv, "--root", str(repo), "--session", NEW])


def test_drop_removes_every_copy_and_lets_the_session_go(
        repo: Path, capsys: pytest.CaptureFixture) -> None:
    old = cmd_intent.open_loop(repo, OLD, DIGEST)
    gate.close(repo, OLD, DIGEST, gate.INTENT_CHANGE)
    assert cmd_intent.run("intent", ["adopt", "--root", str(repo), "--session", NEW]) == 0
    assert _drop(repo, "--digest", "b" * 12) == 0
    assert "dropped" in capsys.readouterr().out
    assert not old.exists() and not cmd_intent.loop_path(repo, NEW, DIGEST).exists()
    assert not gate.is_closed(repo, OLD)


def test_drop_never_guesses_between_two_loops(repo: Path, capsys: pytest.CaptureFixture) -> None:
    one = cmd_intent.open_loop(repo, OLD, DIGEST)
    two = cmd_intent.open_loop(repo, "sc", "sha256:" + "c" * 64)
    assert _drop(repo) == 1
    assert "nothing dropped" in capsys.readouterr().err
    assert one.exists() and two.exists()
    assert _drop(repo, "--from-session", "sc") == 0
    assert one.exists() and not two.exists()
