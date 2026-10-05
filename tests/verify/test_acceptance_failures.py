"""A confirmed example's failing acceptance test is visible where the owner looks: the merge
boundary, ``plumb drift`` and ``plumb status`` (R1, R3, R5)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, commit_all, make_project, write

from plumb import approvals, cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.merge import merge_check
from plumb.verify import open_verify

pytestmark = pytest.mark.sr("SR-027")

INT = "---\nid: INT-001\ntitle: Adding\nquote: q\nreadback: Add numbers.\n---\n"
BROKEN = "def add(a, b):\n    return a - b\n"


@pytest.fixture
def confirmed(repo: Path, write_record) -> tuple[Path, str]:
    """SR-001 confirmed, EX-1 verified_by tests/test_mod.py, passing evidence recorded."""
    make_project(repo)
    write_record(repo, INT)
    write_record(repo, SR_TEXT)
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/pkg/mod.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_mod.py"), example="EX-1")
    commit_all(repo, "base")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()
    approvals.approve(open_core(repo), ["SR-001", "INT-001"])
    assert open_verify(open_core(repo)).run(full=True).ok
    return repo, base


def _regress(root: Path) -> None:
    write(root, "src/pkg/mod.py", BROKEN)
    report = open_verify(open_core(root)).run(nodes=["tests/test_mod.py"])
    assert [r["node"] for r in report.regressions] == ["tests/test_mod.py::test_add"]


def test_requirement_failures_name_examples_and_regressions(confirmed) -> None:
    root, _ = confirmed
    assert open_verify(open_core(root)).requirement_failures() == {}
    _regress(root)
    failures = open_verify(open_core(root)).requirement_failures()
    assert list(failures) == ["SR-001"]
    item = failures["SR-001"][0]
    assert item["test"] == "tests/test_mod.py"
    assert item["examples"] == ["EX-1"]
    assert item["regression"] is True


def test_merge_exits_nonzero_while_a_regression_is_unresolved(confirmed, capsys) -> None:
    root, base = confirmed
    _regress(root)
    code = merge_check(open_core(root), base, as_json=False)
    out = capsys.readouterr().out
    assert code == 5, out
    assert "confirmation: every touched requirement is confirmed" in out
    assert "failing acceptance tests: SR-001 EX-1 tests/test_mod.py (regression)" in out
    assert "regression: tests/test_mod.py::test_add" in out
    code = merge_check(open_core(root), base, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 5 and data["exit"] == 5
    assert data["verification"]["failing"]["SR-001"][0]["examples"] == ["EX-1"]
    # fixed and rerun: the regression is resolved and the boundary passes again
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return a + b\n")
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok
    assert merge_check(open_core(root), base, as_json=False) == 0


def test_drift_and_status_show_the_failing_acceptance_test(confirmed, capsys) -> None:
    root, _ = confirmed
    _regress(root)
    assert cli.main(["drift", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "SR-001 failing acceptance test: EX-1 tests/test_mod.py (regression)" in out
    assert cli.main(["status", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "1 failing (SR-001)" in out
    assert "failing acceptance tests: SR-001 EX-1 tests/test_mod.py (regression)" in out
