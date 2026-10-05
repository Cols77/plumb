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


# -- a failing or unverified acceptance test holds the merge, whatever changed since -------


def _merge(root: Path, base: str, capsys) -> tuple[int, str]:
    code = merge_check(open_core(root), base, as_json=False)
    return code, capsys.readouterr().out


def test_failing_test_that_never_passed_holds_the_merge(confirmed, capsys) -> None:
    root, base = confirmed
    write(root, "tests/test_mod.py", "from pkg.mod import add\n\n\ndef test_add():\n"
          "    assert add(1, 2) == 3\n\n\ndef test_add_neg():\n    assert add(-1, -1) == -3\n")
    report = open_verify(open_core(root)).run(nodes=["tests/test_mod.py"])
    assert report.not_yet_passing == ["tests/test_mod.py::test_add_neg"]
    assert not report.regressions
    code, out = _merge(root, base, capsys)
    assert code == 5, out
    assert "failing acceptance tests: SR-001 EX-1 tests/test_mod.py (failing)" in out
    assert "verification holds the merge" in out


def test_failure_survives_an_edit_until_a_run_passes(confirmed, capsys) -> None:
    root, base = confirmed
    _regress(root)
    write(root, "src/pkg/mod.py", BROKEN + "# unrelated comment\n")  # no rerun
    code, out = _merge(root, base, capsys)
    assert code == 5, out
    assert ("failing acceptance tests: SR-001 EX-1 tests/test_mod.py (regression, stale: "
            "not rerun since the change)") in out
    assert cli.main(["drift", "--root", str(root)]) == 1
    assert "SR-001 failing acceptance test: EX-1 tests/test_mod.py" in capsys.readouterr().out
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return a + b\n")
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok
    assert _merge(root, base, capsys)[0] == 0


def test_acceptance_test_without_passing_evidence_on_current_code_holds_the_merge(
        confirmed, capsys) -> None:
    root, base = confirmed
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")  # not rerun
    code, out = _merge(root, base, capsys)
    assert code == 5, out
    assert "unverified acceptance tests: SR-001 EX-1 tests/test_mod.py (stale since its " \
           "last pass)" in out
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok
    assert _merge(root, base, capsys)[0] == 0


def test_full_run_with_a_failing_test_keeps_full_verification_pending(confirmed) -> None:
    root, _ = confirmed
    write(root, "src/pkg/mod.py", BROKEN)
    report = open_verify(open_core(root)).run(full=True)
    assert report.failed
    pending = open_verify(open_core(root)).full_pending()
    assert pending.pending
    assert any("failed in the last full run" in r for r in pending.reasons), pending
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return a + b\n")
    assert open_verify(open_core(root)).run(nodes=["tests/test_mod.py"]).ok
    pending = open_verify(open_core(root)).full_pending()  # test_twice still failed last
    assert pending.reasons == ("1 test(s) failed in the last full run and have not passed "
                               "since (tests/test_helper.py::test_twice)",)
    assert open_verify(open_core(root)).run(nodes=["tests/test_helper.py"]).ok
    assert not open_verify(open_core(root)).full_pending().pending
