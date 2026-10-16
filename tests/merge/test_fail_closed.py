"""The merge boundary fails closed: a verification that cannot be read never reports green.

Guarantee (sp3 1, 4; "trust comes from evidence"): exit 0 needs verification evidence. When
reading it raises (a corrupt evidence line, a git error in the tree identity, a test-map scan
error) or the verification lane is absent, the report holds with 5 and names the error. The
choke point is ``plumb.boundary.exit_code``; one test per entry point that takes its exit
from it: the library ``merge_report``, ``plumb merge-check``, ``plumb validate --merge`` and
the pre-push hook mode.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from merge_helpers import INT, SR2, commit, git, repin_all, write

import plumb.verify
from plumb import approvals, cli
from plumb.api import open_core
from plumb.boundary import MergeReport, exit_code, merge_report, render
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-254")

SR1 = "---\nid: SR-001\ntitle: Links pin both ends\nstatement: Both ends are pinned.\n---\n"


@pytest.fixture
def green(repo: Path) -> tuple[Path, str]:
    """A change whose only touched requirement is confirmed: exit 0 with verification."""
    write(repo, ".plumb/intents/INT-001.md", INT)
    write(repo, ".plumb/requirements/SR-001.md", SR1)
    write(repo, ".plumb/requirements/SR-002.md", SR2)
    write(repo, "src/mod.py", "x = 1\n")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    sha = commit(repo, "base")
    write(repo, "src/mod.py", "x = 2\n")
    repin_all(repo)
    approvals.approve(open_core(repo), ["SR-001", "INT-001"])
    commit(repo, "change mod\n\nSR: SR-001")
    assert merge_report(open_core(repo), sha, run_full=False).exit == 0
    return repo, sha


@pytest.fixture
def broken(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading the verification state raises, as a corrupt evidence line would."""
    def boom(core):
        raise ValueError("corrupt evidence line 3")

    monkeypatch.setattr(plumb.verify, "open_verify", boom)


def test_exit_code_holds_without_verification() -> None:
    assert exit_code(MergeReport()) == 5
    assert exit_code(MergeReport(verification={"available": False, "error": "x"})) == 5
    assert exit_code(MergeReport(verification={"available": True})) == 0


def test_library_report_holds_when_verification_raises(green, broken) -> None:
    root, sha = green
    for run_full in (False, True):
        report = merge_report(open_core(root), sha, run_full=run_full)
        assert report.exit == 5 and report.evidence is None
        text = "\n".join(render(report))
        assert "verification: unavailable (corrupt evidence line 3); it holds the merge" in text


def test_merge_check_cli_holds(green, broken, capsys) -> None:
    root, sha = green
    assert cli.main(["merge-check", sha, "--no-run", "--root", str(root)]) == 5
    assert "corrupt evidence line 3" in capsys.readouterr().out


def test_validate_merge_holds(green, broken) -> None:
    root, sha = green
    assert cli.main(["validate", "--merge", sha, "--root", str(root)]) == 5


def test_pre_push_hook_mode_holds(green, broken, monkeypatch, capsys) -> None:
    root, sha = green
    head = git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        f"refs/heads/main {head} refs/heads/main {sha}\n"))
    assert cli.main(["merge-check", "--hook", "pre-push", "--no-run",
                     "--root", str(root)]) == 5
    captured = capsys.readouterr()
    assert "corrupt evidence line 3" in captured.out
    assert "the push is refused (merge-check exit 5)" in captured.err
