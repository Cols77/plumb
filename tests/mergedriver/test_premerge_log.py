"""SR-322 EX-3, EX-4: the merge check refuses a merge that deletes a committed log entry
no archive segment keeps."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import commit_all, make_repo, run_git
from iaso import log
from iaso.api import open_core
from iaso.boundary.premerge import check
from iaso.paths import IasoPaths


def _setup(tmp_path: Path) -> tuple[Path, Path, str]:
    """main holding one committed log entry, a feature worktree, main moved on."""
    root = make_repo(tmp_path / "main")
    entry = log.append(IasoPaths(root), "events", "waiver", {"n": 1})  # not telemetry (SR-376)
    commit_all(root, "an entry")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    (root / "notes.txt").write_text("main\n", encoding="utf-8")
    commit_all(root, "main side")
    return root, other, f".iaso/log/{entry.name}"


def _merge(root: Path):
    run_git(root, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-x", check=False)
    return check(open_core(root))


@pytest.mark.sr("SR-322")
def test_ex3_a_deleted_committed_entry_refuses_the_merge(tmp_path: Path) -> None:
    root, other, rel = _setup(tmp_path)
    run_git(other, "rm", "-q", rel)
    commit_all(other, "drop the entry")
    report = _merge(root)
    assert report.exit == 1
    assert any(rel in row for row in report.validate_errors)


@pytest.mark.sr("SR-322")
def test_ex4_an_archived_entry_is_not_refused(tmp_path: Path) -> None:
    root, other, rel = _setup(tmp_path)
    log.archive(IasoPaths(other), [rel.removeprefix(".iaso/log/")])
    commit_all(other, "compact")
    report = _merge(root)
    assert not any(rel in row for row in report.validate_errors)
