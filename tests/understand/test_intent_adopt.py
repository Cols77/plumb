"""SR-302: a session takes over an open intent loop of another session or checkout."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.understand import cmd_intent, files, gate

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


def test_ex3_two_open_loops_and_no_choice_takes_over_neither(
        repo: Path, capsys: pytest.CaptureFixture) -> None:
    """SR-302 EX-3: two sessions run loops; a take-over naming neither changes nothing."""
    old = _opened(repo)
    other = cmd_intent.open_loop(repo, "sc", "sha256:" + "c" * 64)
    before = {p: p.read_text(encoding="utf-8") for p in (old, other)}
    assert _adopt(repo) == 1
    assert "more than one open loop" in capsys.readouterr().err
    assert {p: p.read_text(encoding="utf-8") for p in (old, other)} == before
    assert gate.is_closed(repo, OLD)
    assert _adopt(repo, "--from-session", OLD) == 0


def test_ex1_tasks_and_progress_fields_carry_over_verbatim(repo: Path) -> None:
    old = _opened(repo)
    data = files.read_json(old)
    data.update({"tasks": [{"id": "T1", "state": "done"}], "progress": {"done": 1}})
    files.write_json_atomic(old, data)
    assert _adopt(repo) == 0
    mine = files.read_json(cmd_intent.loop_path(repo, NEW, DIGEST))
    assert mine["tasks"] == data["tasks"] and mine["progress"] == data["progress"]


def test_a_worktree_gate_names_the_loop_left_in_main_and_adopt_takes_an_unclaimed_one(
        repo: Path, tmp_path: Path) -> None:
    """A loop opened in main's checkout holds no intent yet: the worktree's gate says where it
    is and how to take it, adopt matches it by the intent, and the owner's answers follow."""
    old = cmd_intent.open_loop(repo, OLD, DIGEST)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "impl/x", str(wt))
    with pytest.raises(LookupError, match="intent adopt --intent INT-001"):
        cmd_intent._find(wt, NEW, "INT-001")
    from iaso.api import open_core

    open_core(repo).log_append("events", "question-answer", {"session": OLD, "question": "q?"})
    assert _adopt(wt, "--intent", "INT-001") == 0
    assert files.read_json(cmd_intent.loop_path(wt, NEW, DIGEST))["intent"] == "INT-001"
    assert files.read_json(old)["handed_to"]["session"] == NEW
    answers = [e.payload["session"] for e in open_core(wt).events()
               if e.kind == "question-answer"]
    assert answers == [OLD]   # read through the other checkouts, never copied under the new session
