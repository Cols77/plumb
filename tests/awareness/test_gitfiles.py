"""A1: git's worktree and ref files read without running git (SR-079)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, run_git
from plumb.awareness import gitfiles

pytestmark = pytest.mark.sr("SR-258")


def _no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a git process was started")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)


def test_finds_linked_and_main_worktrees_without_git(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    main = make_repo(tmp_path / "main")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    head = run_git(main, "rev-parse", "HEAD").strip()
    _no_git(monkeypatch)
    from_main = gitfiles.worktrees(main)
    from_other = gitfiles.worktrees(other)
    assert [(w.branch, w.main) for w in from_main] == [("main", True), ("feat-x", False)]
    assert [w.path.resolve() for w in from_main] == [w.path.resolve() for w in from_other]
    assert all(w.head == head for w in from_main)
    me = gitfiles.current(other)
    assert me is not None and me.branch == "feat-x" and not me.main
    assert gitfiles.common_dir(other) == gitfiles.common_dir(main)


def test_branch_tips_from_loose_and_packed_refs(tmp_path: Path) -> None:
    main = make_repo(tmp_path / "main")
    run_git(main, "branch", "packed-one")
    run_git(main, "pack-refs", "--all")
    run_git(main, "branch", "loose/two")
    (main / "f.txt").write_text("x\n", encoding="utf-8")
    tip = commit_all(main, "second")
    common = gitfiles.common_dir(main)
    assert common is not None
    tips = gitfiles.branch_tips(common)
    assert tips["main"] == tip                      # a loose ref wins over packed-refs
    assert tips["packed-one"] != tip and len(tips["packed-one"]) == 40
    assert "loose/two" in tips
    assert gitfiles.resolve_ref(common, "refs/heads/packed-one") == tips["packed-one"]


def test_removed_worktree_ignored(tmp_path: Path) -> None:
    """SR-079 EX-4: a worktree removed while git still lists it is ignored."""
    main = make_repo(tmp_path / "main")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    shutil.rmtree(other)
    assert [w.branch for w in gitfiles.worktrees(main)] == ["main"]


def test_outside_git_nothing(tmp_path: Path) -> None:
    assert gitfiles.worktrees(tmp_path) == []
    assert gitfiles.current(tmp_path) is None


def test_loose_object_read_without_git(tmp_path: Path) -> None:
    main = make_repo(tmp_path / "main")
    oid = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=main, input=b"hello\n",
                         capture_output=True, check=True).stdout.decode().strip()
    common = gitfiles.common_dir(main)
    assert common is not None
    assert gitfiles.read_loose_object(common, oid) == ("blob", b"hello\n")
    assert gitfiles.read_loose_object(common, "f" * 40) is None
