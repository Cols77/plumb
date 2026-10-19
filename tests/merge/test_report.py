"""M1: ``plumb.boundary.merge_report``, ``render`` and ``exit_code`` (sp3 3.1, 9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from merge_helpers import INT, SR2, commit, git, repin_all, write

from plumb import approvals, cli
from plumb.api import open_core
from plumb.boundary import MergeReport, exit_code, merge_report, render
from plumb.contracts import Target

SR1 = "---\nid: SR-001\ntitle: Links pin both ends\nstatement: Both ends are pinned.\n---\n"
SR3 = "---\nid: SR-003\ntitle: Third\nstatement: A third behaviour.\n---\n"


@pytest.fixture
def base(repo: Path) -> tuple[Path, str]:
    """INT-001, SR-001 (implemented by src/mod.py), SR-002; no tests."""
    write(repo, ".plumb/intents/INT-001.md", INT)
    write(repo, ".plumb/requirements/SR-001.md", SR1)
    write(repo, ".plumb/requirements/SR-002.md", SR2)
    write(repo, "src/mod.py", "x = 1\n")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo, commit(repo, "base")


@pytest.mark.sr("SR-260")
def test_touched_unconfirmed_is_listed_and_does_not_hold(base) -> None:
    """SR-047 EX-1, SR-260 EX-8: a branch changes a proposed requirement's implementing
    file: listed as waiting on a judge, counted, and not held on."""
    root, sha = base
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    commit(root, "change mod\n\nSR: SR-001")
    report = merge_report(open_core(root), sha, run_full=False)
    assert isinstance(report, MergeReport)
    assert report.touched == ("SR-001",)
    assert [a["id"] for a in report.awaiting] == ["SR-001", "INT-001"]
    assert exit_code(report) == 0 == report.exit
    text = "\n".join(render(report))
    assert "SR-001 (proposed) Links pin both ends" in text
    assert "plumb: waiting on a judge: 2 records" in text     # counted (SR-267)
    assert "plumb approve" not in text


@pytest.mark.sr("SR-260")
def test_validate_merge_and_merge_check_agree(base, capsys) -> None:
    """SR-047 EX-3: the report-only form and merge-check exit with the same code."""
    root, sha = base
    args = ["--root", str(root)]
    write(root, "src/mod.py", "x = 2\n")  # uncommitted, link stale: exit 1
    assert cli.main(["validate", "--merge", sha, *args]) == 1
    assert cli.main(["merge-check", sha, "--no-run", *args]) == 1
    repin_all(root)  # touched and unconfirmed: listed, exit 0 (SR-260 EX-8)
    assert cli.main(["validate", "--merge", sha, *args]) == 0
    assert cli.main(["merge-check", sha, "--no-run", *args]) == 0
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    assert cli.main(["validate", "--merge", sha, *args]) == 0
    assert cli.main(["merge-check", sha, "--no-run", *args]) == 0
    capsys.readouterr()
    assert cli.main(["merge-check", sha, "--no-run", "--json", *args]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["exit"] == 0 and data["touched"] == ["SR-001"]


def _escalated(root: Path) -> None:
    write(root, ".plumb/intents/INT-002.md",
          "---\nid: INT-002\ntitle: Escalated spec\nquote: q\nreadback: r\nmode: escalated\n"
          "members: [SR-001, SR-003]\n---\n")
    write(root, ".plumb/requirements/SR-003.md", SR3)


@pytest.mark.sr("SR-260")
def test_set_member_counts_only_with_full_set_approval(base) -> None:
    """A touched member of an escalated set is confirmed only by an approval that pins
    every member's current hash."""
    root, _ = base
    _escalated(root)
    sha = commit(root, "escalated set")
    approvals.approve(open_core(root), ["SR-001", "INT-001"])  # one member alone
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    report = merge_report(open_core(root), sha, run_full=False)
    states = {a["id"]: a["state"] for a in report.awaiting}
    assert states == {"SR-001": "set unconfirmed"}
    assert report.exit == 0       # listed, never held (SR-260)
    assert "INT-002" in "\n".join(render(report))
    approvals.approve(open_core(root), ["SR-001", "SR-003"])  # the whole set
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.awaiting == () and report.exit == 0


@pytest.mark.sr("SR-260")
def test_range_error_exits_2(base) -> None:
    root, _ = base
    report = merge_report(open_core(root), "no-such-ref", run_full=False)
    assert report.exit == 2 and report.error
    assert "cannot read the range" in render(report)[0]


@pytest.mark.sr("SR-260")
def test_report_covers_uncommitted_and_branch(base) -> None:
    root, _ = base
    git(root, "checkout", "-q", "-b", "feat")
    write(root, "notes.txt", "n\n")
    commit(root, "notes\n\nSR: SR-002")
    report = merge_report(open_core(root), "main", run_full=False)
    assert report.touched == ("SR-002",) and report.fork
