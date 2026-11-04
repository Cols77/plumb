"""A full run of the merged tree recorded in any checkout of this machine counts at the merge
check: main's own log cannot see the green run a branch's worktree recorded, so every landing
that changed pyproject.toml read "full suite pending" (report-d188e19d)."""

from __future__ import annotations

from pathlib import Path

import pytest
from merge_helpers import git, project, write

from plumb.api import open_core
from plumb.boundary.premerge import check
from plumb.merge import _verification
from plumb.verify import open_verify

pytestmark = pytest.mark.sr("SR-254")


def commit(root: Path, message: str) -> str:
    """A commit without the log: a worktree's own runs stay in its checkout, as in a real
    landing, so main can only see them across checkouts."""
    git(root, "add", "-A", "--", ".", ":!.plumb/log")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()

BUMP = 'version = "0.2.0"\n'
ENV_GATED = ("import os\n\nfrom pkg.mod import add\n\n\ndef test_add():\n"
             "    assert add(1, 2) == 3 and not os.environ.get('FULLRUN_RED')\n")


@pytest.fixture
def landing(repo: Path, tmp_path: Path) -> tuple[Path, Path, str]:
    """main with a full run recorded, and a worktree whose branch bumped pyproject.toml."""
    project(repo)
    before = commit(repo, "project")
    open_verify(open_core(repo)).run(full=True)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "fix", str(wt))
    pyproject = (wt / "pyproject.toml").read_text(encoding="utf-8")
    write(wt, "pyproject.toml", BUMP + pyproject)
    commit(wt, "bump")
    return repo, wt, before


def _pending(root: Path, base: str) -> dict:
    return _verification(open_core(root), [], ["pyproject.toml"], base)


def test_green_run_in_the_worktree_counts_after_a_fast_forward(landing) -> None:
    repo, wt, before = landing
    open_verify(open_core(wt)).run(full=True)
    git(repo, "merge", "-q", "--ff-only", "fix")
    report = check(open_core(repo), fast_forward=(before, git(repo, "rev-parse", "HEAD").strip(),
                                                  "fix"))
    assert not any("full test suite is pending" in line for line in report.verify_lines), \
        report.verify_lines


def test_a_worktree_past_the_sibling_cap_still_counts(landing, monkeypatch) -> None:
    """More worktrees than the owner-words reads consult (SIBLING_MAX): the landing's own
    worktree is still read for its full run."""
    from plumb import log

    repo, wt, before = landing
    open_verify(open_core(wt)).run(full=True)
    monkeypatch.setattr(log, "SIBLING_MAX", 0)
    git(repo, "merge", "-q", "--ff-only", "fix")
    assert not _pending(repo, before)["full_pending"]


def test_green_run_counts_when_only_records_moved_after_it(landing) -> None:
    """A repin after the tests passed changes the tree only under .plumb/."""
    repo, wt, before = landing
    open_verify(open_core(wt)).run(full=True)
    record = wt / ".plumb/requirements/SR-002.md"
    record.write_text(record.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    commit(wt, "repin")
    git(repo, "merge", "-q", "--ff-only", "fix")
    assert not _pending(repo, before)["full_pending"]


def test_without_a_run_of_this_tree_it_stays_pending(landing) -> None:
    repo, _wt, before = landing
    git(repo, "merge", "-q", "--ff-only", "fix")
    found = _pending(repo, before)
    assert found["full_pending"] and "pyproject.toml changed" in found["full_pending_reasons"]


def test_a_run_of_another_tree_does_not_count(landing) -> None:
    repo, wt, before = landing
    open_verify(open_core(wt)).run(full=True)
    write(wt, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    commit(wt, "later code")
    git(repo, "merge", "-q", "--ff-only", "fix")
    assert _pending(repo, before)["full_pending"]


def test_a_run_on_a_dirty_tree_does_not_count(landing) -> None:
    repo, wt, before = landing
    write(wt, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    open_verify(open_core(wt)).run(full=True)
    git(repo, "merge", "-q", "--ff-only", "fix")
    assert _pending(repo, before)["full_pending"]


def test_a_later_red_run_of_the_tree_wins(landing, monkeypatch) -> None:
    repo, wt, before = landing
    write(wt, "tests/test_mod.py", ENV_GATED)
    commit(wt, "a test the environment can fail")
    open_verify(open_core(wt)).run(full=True)
    monkeypatch.setenv("FULLRUN_RED", "1")
    open_verify(open_core(wt)).run(full=True)
    monkeypatch.delenv("FULLRUN_RED")
    git(repo, "merge", "-q", "--ff-only", "fix")
    assert _pending(repo, before)["full_pending"]


def test_a_change_in_the_checkout_merging_keeps_it_pending(landing) -> None:
    """The merged tree is what the index holds; a working file that differs from it is not it."""
    repo, wt, before = landing
    open_verify(open_core(wt)).run(full=True)
    git(repo, "merge", "-q", "--ff-only", "fix")
    write(repo, "pyproject.toml", "# edited, not staged\n")
    assert _pending(repo, before)["full_pending"]
