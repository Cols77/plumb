"""SR-306: the merge check refuses a landing while validate shows any error or a link is left stale."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import commit_all, ex, make_repo, plumb, record, run_git, write_record
from plumb.api import open_core
from plumb.boundary.premerge import check


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    """main and feat-x, SR-005 linked to src/a.py in both; main has moved on."""
    root = make_repo(tmp_path / "main")
    write_record(root, record(statement="A relay pins every stated record.", examples=[ex(1)]))
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert plumb(root, "link", "SR-005", "implemented_by", "src/a.py").returncode == 0
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    (root / "notes.txt").write_text("main\n", encoding="utf-8")
    commit_all(root, "main side")
    return root, other


def _merge(root: Path):
    run_git(root, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-x", check=False)
    return check(open_core(root))



@pytest.mark.sr("SR-306")
def test_ex1_a_validate_error_already_on_main_refuses_the_merge(tmp_path: Path) -> None:
    root, other = _pair(tmp_path)
    (root / ".plumb" / "requirements" / "SR-005.md").write_text("not a record\n", encoding="utf-8")
    commit_all(root, "break main\n\nSR: SR-005")
    (other / "other.txt").write_text("feat\n", encoding="utf-8")
    commit_all(other, "plain")
    report = _merge(root)
    assert report.exit == 1 and report.validate_errors
    assert "validate errors in the records" in "\n".join(report.lines)


@pytest.mark.sr("SR-306")
def test_ex2_a_link_left_stale_names_the_repin(tmp_path: Path) -> None:
    root, other = _pair(tmp_path)
    (other / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    commit_all(other, "edit\n\nSR: SR-005")
    report = _merge(root)
    assert report.exit == 1 and any("SR-005#" in line for line in report.stale_links)
    assert "repin each once its tests pass" in "\n".join(report.lines)


@pytest.mark.sr("SR-306")
def test_ex3_a_link_stale_at_the_base_does_not_hold(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "main")
    write_record(root, record(statement="A relay pins every stated record.", examples=[ex(1)]))
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert plumb(root, "link", "SR-005", "implemented_by", "src/a.py").returncode == 0
    commit_all(root, "SR-005")
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    commit_all(root, "stale before the fork")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    (other / "notes.txt").write_text("feat\n", encoding="utf-8")
    commit_all(other, "unrelated\n\nSR: SR-005")
    (root / "notes2.txt").write_text("main\n", encoding="utf-8")
    commit_all(root, "main side")
    report = _merge(root)
    assert report.stale_links == () and report.validate_errors == ()


@pytest.mark.sr("SR-306")
def test_ex4_a_clean_branch_goes_through(tmp_path: Path) -> None:
    root, other = _pair(tmp_path)
    (other / "other.txt").write_text("feat\n", encoding="utf-8")
    commit_all(other, "plain")
    report = _merge(root)
    assert report.exit == 0 and not report.validate_errors and not report.stale_links
