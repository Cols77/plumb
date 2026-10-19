"""SR-260 EX-10: the quick check (``premerge.check``, no test run) and the report-only form
(``merge_report(run_full=False)``) exit with the same code on the same merge in progress: a
linked test never run (EX-19, SR-254), a failing linked test (rule (c)), a failing test beside an
open owner question (EX-6: 5 before 4), a malformed claims.yaml (listed, never held)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from merge_helpers import commit, git, project, repin_all, write

from plumb import approvals
from plumb.api import open_core
from plumb.boundary import merge_report, render
from plumb.boundary.premerge import check

pytestmark = pytest.mark.sr("SR-260")


@pytest.fixture
def merging(repo: Path) -> Path:
    """main holds confirmed SR-001 (verified_by tests/test_mod.py); feat changes its code with
    no SR trailer (no proof is delivered); main moved; ``git merge --no-commit feat``."""
    project(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    commit(repo, "project")
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    repin_all(repo)
    commit(repo, "reorder add")
    git(repo, "checkout", "-q", "main")
    write(repo, "notes.txt", "main side\n")
    commit(repo, "notes")
    git(repo, "merge", "--no-commit", "--no-ff", "--no-verify", "feat")
    return repo


def _both(root: Path) -> tuple[int, int, str]:
    quick = check(open_core(root))
    report = merge_report(open_core(root), "HEAD", run_full=False)
    return quick.exit, report.exit, "\n".join([*quick.lines, *render(report)])


def _run(root: Path, broken: bool) -> None:
    from plumb.verify import open_verify

    if broken:
        write(root, "src/pkg/mod.py", "def add(a, b):\n    return a - b\n")
        repin_all(root)
    open_verify(open_core(root)).run(full=True)
    git(root, "add", "-A")      # the merge result carries the change and its evidence


def test_a_test_never_run_holds_both_forms_alike(merging: Path) -> None:
    """EX-10, EX-19: no test run since the change: both forms exit 5, the quick check names
    what holds it without running a test."""
    quick, report, text = _both(merging)
    assert quick == report == 5, text


def test_a_failing_linked_test_holds_both_forms_with_5(merging: Path) -> None:
    """Rule (c): the latest recorded run of SR-001's test fails: 5 in both forms, the quick
    check naming the test by the requirement's title."""
    _run(merging, broken=True)
    quick = check(open_core(merging))
    assert quick.exit == 5, quick.lines
    assert [(r["id"], r["state"]) for r in quick.failing_tests] == [("SR-001", "failing")]
    assert '"add returns the sum": tests/test_mod.py (failing)' in "\n".join(quick.lines)
    assert merge_report(open_core(merging), "HEAD", run_full=False).exit == 5


def test_a_passing_run_lets_both_forms_through(merging: Path) -> None:
    _run(merging, broken=False)
    quick, report, text = _both(merging)
    assert quick == report == 0, text


def test_a_failing_test_beside_an_open_question_exits_5(merging: Path) -> None:
    """EX-6: precedence 1, then 5, then 4."""
    _run(merging, broken=True)
    write(merging, ".plumb/requirements/SR-001.md", (merging / ".plumb/requirements/SR-001.md")
          .read_text(encoding="utf-8").replace("returns a + b.", "returns the sum a + b."))
    repin_all(merging)
    git(merging, "add", "-A")     # reworded in the merge: unconfirmed, so the judge asks
    core = open_core(merging)
    path = merging / ".plumb" / "session" / "s1" / "judge_questions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "key": "should add sum?", "question": "Should add sum?", "header": "Add", "job": "j1",
        "options": [{"label": "yes", "description": ""}],
        "records": [{"id": "SR-001", "hash": core.index()["SR-001"].hash}]}]),
        encoding="utf-8")
    quick = check(open_core(merging))
    report = merge_report(open_core(merging), "HEAD", run_full=False)
    assert quick.questions and report.questions
    assert quick.exit == report.exit == 5, [*quick.lines, *render(report)]


def test_a_malformed_claims_policy_is_listed_by_both_and_holds_neither(merging: Path) -> None:
    _run(merging, broken=False)
    write(merging, ".plumb/claims.yaml", "exempt: not-a-list\n")
    git(merging, "add", "-A")
    quick, report, text = _both(merging)
    assert quick == report == 0, text
    assert "exempt must be a list of globs" in text
