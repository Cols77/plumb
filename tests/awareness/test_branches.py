"""A3: branches without a worktree, scanned at session start only (SR-078, SR-079)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from awareness.gitrepo import commit_all, make_repo, requirement, run_git
from plumb import awareness
from plumb.api import open_core
from plumb.awareness import publish as pub
from plumb.awareness import scan


def _repo(tmp_path: Path) -> Path:
    main = make_repo(tmp_path / "main")
    for n in range(1, 10):
        requirement(main, f"SR-00{n}", f"thing {n}")
    commit_all(main, "records")
    return main


def _branch(main: Path, name: str, record: str, statement: str) -> None:
    run_git(main, "checkout", "-q", "-b", name)
    requirement(main, record, f"thing {record[-1]}", statement)
    commit_all(main, f"{name} edits {record}")
    run_git(main, "checkout", "-q", "main")


def _working_on(main: Path, *records: str) -> None:
    for record in records:
        requirement(main, record, f"thing {record[-1]}", "main's own edit")
    pub.publish(open_core(main), [f".plumb/requirements/{r}.md" for r in records])


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    real = subprocess.run

    def counting(args, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        calls.append(list(args))
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    return calls


@pytest.mark.sr("SR-258")
def test_branch_without_worktree_reported_at_session_start(tmp_path: Path) -> None:
    """SR-078 EX-3: a branch without a worktree whose commits changed SR-007."""
    main = _repo(tmp_path)
    _branch(main, "feat-y", "SR-007", "feat-y's version")
    _working_on(main, "SR-007")
    assert awareness.brief_lines(open_core(main)) == [
        'plumb: SR-007 "thing 7" is also being changed on branch feat-y']


@pytest.mark.sr("SR-258")
def test_unmoved_tip_runs_no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-079 EX-2: a branch whose tip has not moved since the last scan runs no git."""
    main = _repo(tmp_path)
    _branch(main, "feat-y", "SR-007", "feat-y's version")
    _working_on(main, "SR-007")
    awareness.brief_lines(open_core(main))
    calls = _counting(monkeypatch)
    lines = awareness.brief_lines(open_core(main))
    assert [c for c in calls if c[:2] == ["git", "diff"]] == []
    assert lines and "feat-y" in lines[0]


@pytest.mark.sr("SR-258")
def test_scan_capped_by_branch_max(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = _repo(tmp_path)
    for n in range(1, 5):
        _branch(main, f"b{n}", f"SR-00{n}", f"b{n}'s version")
    (main / ".plumb" / "config.yaml").write_text("awareness: {branch_max: 2}\n",
                                                 encoding="utf-8")
    calls = _counting(monkeypatch)
    scan.refresh_branches(open_core(main))
    assert len([c for c in calls if c[:2] == ["git", "diff"]]) == 2
    calls.clear()
    cache = scan.refresh_branches(open_core(main))     # the rest at a later session start
    assert len([c for c in calls if c[:2] == ["git", "diff"]]) == 2
    assert sorted(cache["branches"]) == ["b1", "b2", "b3", "b4"]


@pytest.mark.sr("SR-258")
def test_scan_capped_by_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = _repo(tmp_path)
    _branch(main, "b1", "SR-001", "b1's version")

    class Spent:
        def expired(self) -> bool:
            return True

    calls = _counting(monkeypatch)
    scan.refresh_branches(open_core(main), deadline=Spent())
    assert [c for c in calls if c[:2] == ["git", "diff"]] == []
    errors = (main / ".plumb" / "session" / "errors.log").read_text(encoding="utf-8")
    assert "awareness skipped (budget)" in errors


@pytest.mark.sr("SR-258")
def test_default_branch_skipped(tmp_path: Path) -> None:
    main = _repo(tmp_path)
    run_git(main, "checkout", "-q", "-b", "side")
    requirement(main, "SR-001", "thing 1", "main moves on")
    run_git(main, "checkout", "-q", "main")
    run_git(main, "merge", "-q", "--no-ff", "-m", "noop", "side")
    run_git(main, "checkout", "-q", "-b", "work")
    cache = scan.refresh_branches(open_core(main), skip=["work"])
    assert "main" not in cache["branches"]
