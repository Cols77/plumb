"""SR-302: a session takes over an open intent loop of another session or checkout."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.understand import cmd_intent, files, gate

from conftest import git

pytestmark = pytest.mark.sr("SR-302")

OLD, NEW = "sa", "sb"
DIGEST = "sha256:" + "b" * 64


def _adopt(repo: Path, *argv: str) -> int:
    return cmd_intent.run("intent", ["adopt", *argv, "--root", str(repo), "--session", NEW])


def _opened(repo: Path) -> Path:
    path = cmd_intent.open_loop(repo, OLD, DIGEST)
    data = files.read_json(path)
    data["intent"] = "INT-001"
    data["stages"]["clarify"] = {"state": "passed"}
    files.write_json_atomic(path, data)
    gate.close(repo, OLD, DIGEST, gate.INTENT_CHANGE)
    return path


def test_ex1_the_stages_carry_over_and_the_old_copy_says_handed_over(
        repo: Path, capsys: pytest.CaptureFixture) -> None:
    old = _opened(repo)
    assert _adopt(repo) == 0
    mine = files.read_json(cmd_intent.loop_path(repo, NEW, DIGEST))
    assert mine["intent"] == "INT-001" and mine["stages"]["clarify"]["state"] == "passed"
    assert mine["stages"]["plan"] == {"state": "open"}
    assert files.read_json(old)["handed_to"]["session"] == NEW
    assert not gate.is_closed(repo, OLD)
    capsys.readouterr()
    assert cmd_intent.run("intent", ["status", "--root", str(repo), "--session", OLD]) == 0
    assert "no intent loop is open" in capsys.readouterr().out


def test_ex2_a_worktree_takes_over_a_loop_opened_in_the_main_checkout(
        repo: Path, tmp_path: Path) -> None:
    old = _opened(repo)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "impl/x", str(wt))
    assert _adopt(wt) == 0
    assert files.read_json(cmd_intent.loop_path(wt, NEW, DIGEST))["intent"] == "INT-001"
    assert files.read_json(old)["handed_to"]["session"] == NEW


def test_ex3_nothing_matches_says_so_and_changes_nothing(
        repo: Path, capsys: pytest.CaptureFixture) -> None:
    old = _opened(repo)
    before = old.read_text(encoding="utf-8")
    assert _adopt(repo, "--intent", "INT-999") == 1
    assert "nothing taken over" in capsys.readouterr().err
    assert old.read_text(encoding="utf-8") == before
    assert not cmd_intent.loop_path(repo, NEW, DIGEST).exists()
