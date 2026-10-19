"""SR-296 EX-7 (a held merge finished by hand starts the landing), SR-320 EX-9 (a loop living in
the worktree keeps it), SR-329 (the tidy commit takes main's shared log entries)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from boundary.test_landing import docs, head, land_branch
from core.test_log_compaction import put
from mergedriver.mdhelpers import commit_all, run_git
from plumb.boundary import landing
from plumb.boundary.premerge import install_land_hook, unstaged_plumb


@pytest.mark.sr("SR-296")
def test_ex7_a_held_merge_finished_with_git_commit_starts_the_landing(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUMB_FAKE_DISPATCH", "1")
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2] / "src"))
    install_land_hook(repo, sys.executable)
    run_git(repo, "checkout", "-q", "-b", "feat")
    docs(repo, "x.txt")
    commit_all(repo, "feat")
    run_git(repo, "checkout", "-q", "main")
    run_git(repo, "merge", "-q", "--no-ff", "--no-commit", "feat")
    run_git(repo, "commit", "-q", "-m", "m")
    sha = head(repo)
    for _ in range(300):  # the landing job runs detached
        if landing.marker(repo, sha).exists():
            break
        time.sleep(0.1)
    assert landing.marker(repo, sha).exists()


def _tree_with_loop(repo: Path, tmp_path: Path) -> Path:
    tree = tmp_path / "wt-feat"
    run_git(repo, "worktree", "add", "-q", "-b", "feat", str(tree))
    docs(tree, "work.md")
    commit_all(tree, "work")
    path = tree / ".plumb" / "session" / "s9" / "intent" / "abc.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"intent": "INT-001", "stages": {"clarify": {"state": "open"}}}),
                    "utf-8")  # an adopted loop: it names no path and no branch
    return tree


@pytest.mark.sr("SR-320")
def test_ex9_an_open_loop_in_the_worktrees_own_session_keeps_it(repo: Path,
                                                                 tmp_path: Path) -> None:
    tree = _tree_with_loop(repo, tmp_path)
    before = head(repo)
    run_git(repo, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "feat")
    removed, kept = landing.finished_worktrees(repo, before, head(repo))
    assert tree.exists() and removed == []
    assert kept == ["worktree wt-feat finished but kept: an open intent loop lives there"]


def _entries(repo: Path) -> set[str]:
    out = run_git(repo, "status", "--porcelain", "--untracked-files=all", "--", ".plumb/log")
    return {line[3:] for line in out.stdout.splitlines()}


@pytest.mark.sr("SR-329")
def test_ex1_ex2_the_tidy_commit_takes_every_shared_entry_and_no_local_one(repo: Path) -> None:
    sha, before = land_branch(repo, lambda root: docs(root, "x.txt"))
    for n, kind in enumerate(["judgment", "approval", "prompt"] * 3):
        put(repo, kind, {"n": n})
    put(repo, "verdict", {"n": 1})
    landing.land(repo, sha, before)
    assert {p for p in _entries(repo) if "/verdict/" not in p} == set()
    shown = run_git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sum(p.startswith(".plumb/log/judgment/") for p in shown) == 3
    assert not any("/verdict/" in p for p in shown)
    assert list((repo / ".plumb" / "log" / "verdict").glob("*.json"))


@pytest.mark.sr("SR-329")
def test_ex3_main_s_own_uncommitted_shared_entries_do_not_hold_a_merge(repo: Path) -> None:
    put(repo, "judgment", {"n": 1})
    assert unstaged_plumb(repo) == []
    (repo / ".plumb" / "requirements").mkdir(exist_ok=True)
    (repo / ".plumb" / "requirements" / "SR-900.md").write_text("x\n", encoding="utf-8")
    assert unstaged_plumb(repo) == [".plumb/requirements/SR-900.md"]


@pytest.mark.sr("SR-329")
def test_ex4_an_entry_written_after_one_tidy_commit_is_taken_by_the_next(repo: Path) -> None:
    sha, before = land_branch(repo, lambda root: docs(root, "x.txt"))
    put(repo, "judgment", {"n": 1})
    landing.land(repo, sha, before)
    assert _entries(repo) == set()
    run_git(repo, "checkout", "-q", "-b", "feat2")
    docs(repo, "y.txt")
    commit_all(repo, "feat2")
    run_git(repo, "checkout", "-q", "main")
    run_git(repo, "merge", "-q", "--no-ff", "--no-verify", "-m", "m2", "feat2")
    put(repo, "judgment", {"n": 2})
    assert len(_entries(repo)) == 1
    landing.land(repo, head(repo), sha)
    assert _entries(repo) == set()
