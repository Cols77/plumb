"""M4: the claims, link and log-integrity gates (exit 1) and the exit precedence 1, 5, 4
(sp3 5, SR-049)."""

from __future__ import annotations

from pathlib import Path

import pytest
from merge_helpers import commit, project, repin_all, write

from plumb import approvals
from plumb.api import open_core
from plumb.boundary import merge_report, render

pytestmark = pytest.mark.sr("SR-049")


@pytest.fixture
def confirmed(repo: Path) -> tuple[Path, str]:
    project(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    return repo, commit(repo, "project")


def _text(report) -> str:
    return "\n".join(render(report))


def test_undeclared_path_exits_1(confirmed) -> None:
    """SR-049 EX-1: a commit claiming SR-002 changes a path SR-002 does not declare."""
    root, sha = confirmed
    write(root, "src/pkg/extra.py", "y = 1\n")
    commit(root, "extra\n\nSR: SR-002")
    report = merge_report(open_core(root), sha, run_full=False)
    assert [u["path"] for u in report.claims["undeclared"]] == ["src/pkg/extra.py"]
    assert report.exit == 1
    text = _text(report)
    assert "undeclared path src/pkg/extra.py" in text
    assert "plumb link SR-002 implemented_by src/pkg/extra.py" in text


def test_unclaimed_commit_with_required_trailer_exits_1(confirmed) -> None:
    root, sha = confirmed
    write(root, ".plumb/claims.yaml", "require_trailer: true\n")
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    repin_all(root)
    commit(root, "no trailer")
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.claims["unclaimed_commits"] and report.exit == 1
    assert "no SR: trailer" in _text(report)


def test_stale_link_on_touched_record_exits_1(confirmed) -> None:
    """SR-049 EX-2: the implemented_by end moved and was not repinned."""
    root, sha = confirmed
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    report = merge_report(open_core(root), sha, run_full=False)
    stale = [row for row in report.links if row["state"] == "stale"]
    assert [row["link"] for row in stale] == ["SR-001#1"]
    assert report.exit == 1
    text = _text(report)
    assert "stale link SR-001#1 implemented_by src/pkg/mod.py (target moved)" in text
    assert "plumb repin SR-001#1" in text


def test_dangling_link_exits_1(confirmed) -> None:
    root, sha = confirmed
    (root / "src" / "pkg" / "mod.py").unlink()
    report = merge_report(open_core(root), sha, run_full=False)
    assert any(row["state"] == "dangling" and row["link"] == "SR-001#1"
               for row in report.links)
    assert report.exit == 1
    assert "dangling link SR-001#1" in _text(report)


def test_exit_precedence_1_5_4(confirmed) -> None:
    """SR-049 EX-3: a failing confirmed acceptance test beats an unconfirmed touched record;
    a broken log beats both."""
    root, sha = confirmed
    from plumb.verify import open_verify

    write(root, "src/pkg/mod.py", "def add(a, b):\n    return a - b\n")
    open_verify(open_core(root)).run(nodes=["tests/test_mod.py"])
    write(root, ".plumb/requirements/SR-002.md",
          "---\nid: SR-002\ntitle: Other\nstatement: Changed.\n---\n")
    write(root, "notes.txt", "n\n")
    repin_all(root)
    commit(root, "break add\n\nSR: SR-001\nSR: SR-002")
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.failing and any(a["id"] == "SR-002" for a in report.awaiting)
    assert report.claims["undeclared"] and report.exit == 1  # notes.txt is undeclared
    write(root, ".plumb/claims.yaml", "exempt: [notes.txt]\n")
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.exit == 5, _text(report)
    events = root / ".plumb" / "log" / "events.jsonl"
    events.write_text(events.read_text(encoding="utf-8").replace("INT-001", "SR-009", 1),
                      encoding="utf-8")
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.integrity and report.exit == 1
