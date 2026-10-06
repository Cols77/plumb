"""M3: exactly one full-suite run per merge-check, reuse on an identical identity, and the
``merge-evidence`` event on green (sp3 4, SR-048). The runner is the real one, wrapped by a
fake that counts its calls."""

from __future__ import annotations

from pathlib import Path

import pytest
from merge_helpers import commit, project, repin_all, write

from plumb import approvals
from plumb.api import open_core
from plumb.boundary import merge_report, render
from plumb.verify import open_verify

pytestmark = pytest.mark.sr("SR-048")

FAILING = ("from pkg.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 4\n")


class Counting:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, core):
        self.calls += 1
        return open_verify(core).run(full=True)


def _evidence(root: Path) -> list:
    return list(open_core(root).log_read("evidence", ["merge-evidence"]))


@pytest.fixture
def confirmed(repo: Path) -> tuple[Path, str]:
    """The project, every record confirmed, committed; no full run recorded yet."""
    project(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    return repo, commit(repo, "project")


def test_pending_cleared_by_one_green_run(confirmed) -> None:
    root, sha = confirmed
    assert open_verify(open_core(root)).full_pending().pending
    runner = Counting()
    report = merge_report(open_core(root), sha, runner=runner)
    assert runner.calls == 1
    assert report.full_run["needed"] and report.full_run["ran"]
    assert report.full_run["verdict"] == "passed" and report.full_run["run_id"]
    assert not open_verify(open_core(root)).full_pending().pending
    assert report.exit == 0, render(report)


def test_infra_change_runs_once_and_clears(confirmed) -> None:
    """SR-048 EX-1: uv.lock changed since the last full run."""
    root, _ = confirmed
    open_verify(open_core(root)).run(full=True)
    sha = commit(root, "evidence")
    write(root, "uv.lock", "version = 1\n")
    assert open_verify(open_core(root)).full_pending().pending
    runner = Counting()
    report = merge_report(open_core(root), sha, runner=runner)
    assert runner.calls == 1 and report.full_run["verdict"] == "passed"
    assert any("uv.lock" in r for r in report.full_run["reasons"])
    assert not open_verify(open_core(root)).full_pending().pending


def test_red_run_not_repeated_and_holds_5(repo: Path) -> None:
    """SR-048 EX-2: a failing full run runs once, exits 5 and writes no merge evidence."""
    project(repo, test=FAILING)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    sha = commit(repo, "project")
    runner = Counting()
    report = merge_report(open_core(repo), sha, runner=runner)
    assert runner.calls == 1
    assert report.full_run["ran"] and report.full_run["verdict"] == "failed"
    assert report.exit == 5
    assert _evidence(repo) == []
    assert any("full run" in line and "failed" in line for line in render(report))


def test_identical_identity_reuses(confirmed) -> None:
    """SR-048 EX-3: a passing full run on the same tree and environment is reused."""
    root, sha = confirmed
    first = open_verify(open_core(root)).run(full=True)
    runner = Counting()
    report = merge_report(open_core(root), sha, runner=runner)
    assert runner.calls == 0
    assert report.full_run["reused"] and report.full_run["run_id"] == first.run_id
    assert f"full run reused (run {first.run_id})" in "\n".join(render(report))
    assert report.exit == 0


def test_no_run_flag_runs_nothing(confirmed) -> None:
    root, sha = confirmed
    runner = Counting()
    report = merge_report(open_core(root), sha, run_full=False, runner=runner)
    assert runner.calls == 0
    assert report.full_run["needed"] and not report.full_run["ran"]
    assert report.exit == 5
    assert _evidence(root) == []


def test_merge_evidence_only_on_green(confirmed) -> None:
    root, sha = confirmed
    report = merge_report(open_core(root), sha, runner=Counting())
    assert report.exit == 0
    entries = _evidence(root)
    assert len(entries) == 1
    payload = entries[0].payload
    assert payload["verdict"] == "green" and payload["full_run"] == report.full_run["run_id"]
    assert payload["reused"] is False and payload["head_tree"] and "dirty" in payload
    assert payload["env"]["env_key"] and payload["base"] == sha
    # a second green check of the same identity reuses the run and adds no duplicate entry
    again = merge_report(open_core(root), sha, runner=Counting())
    assert again.full_run["reused"] and len(_evidence(root)) == 1
    # an unconfirmed touched record: not green, nothing written
    write(root, ".plumb/requirements/SR-002.md",
          "---\nid: SR-002\ntitle: Other\nstatement: Something new.\n---\n")
    repin_all(root)
    waiting = merge_report(open_core(root), sha, runner=Counting())
    assert waiting.exit == 4 and len(_evidence(root)) == 1
