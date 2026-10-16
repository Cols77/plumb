"""V6: the regression rule, exactly as R3 (spec 7.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from plumb.api import open_core
from plumb.verify import open_verify
from plumb.verify.evidence import apply_entry, single_evidence
from plumb.verify.policy import is_regression, regression_instruction


def _run(index: dict, run_id: str, outcomes: dict[str, str], test_hash: str = "T") -> None:
    apply_entry(index, {"run_id": run_id, "env": {"env_key": "E"},
                        "nodes": [{"id": n, "outcome": o, "closure": "C", "test_hash": test_hash}
                                  for n, o in outcomes.items()]})


@pytest.fixture
def project(repo: Path) -> Path:
    make_project(repo)
    commit_all(repo)
    return repo


@pytest.mark.sr("SR-254")
def test_regression_requires_prior_pass_of_same_node() -> None:
    index: dict = {"nodes": {}, "full": None}
    _run(index, "r1", {"t.py::a": "passed"})
    _run(index, "r2", {"t.py::b": "failed"})
    assert is_regression(index, "t.py::b") is False
    _run(index, "r3", {"t.py::a": "failed"})
    assert is_regression(index, "t.py::a") is True
    ev = single_evidence(index, "t.py::a", closure="C", test_hash="T", env_key="E")
    assert ev.regression is True and ev.test_changed_since_pass is False
    _run(index, "r4", {"t.py::a": "passed"})
    assert is_regression(index, "t.py::a") is False


@pytest.mark.sr("SR-254")
def test_flaky_pass_counts_as_prior_pass() -> None:
    index: dict = {"nodes": {}, "full": None}
    _run(index, "r1", {"t.py::a": "flaky"})
    _run(index, "r2", {"t.py::a": "failed"})
    assert is_regression(index, "t.py::a") is True


@pytest.mark.sr("SR-254")
def test_never_passed_existing_node_is_not_regression() -> None:
    index: dict = {"nodes": {}, "full": None}
    _run(index, "r1", {"t.py::a": "failed"})
    _run(index, "r2", {"t.py::a": "failed"})
    _run(index, "r3", {"t.py::a": "skipped"})
    _run(index, "r4", {"t.py::a": "failed"})
    assert is_regression(index, "t.py::a") is False


@pytest.mark.sr("SR-254")
def test_regression_notes_test_source_changed() -> None:
    index: dict = {"nodes": {}, "full": None}
    _run(index, "r1", {"t.py::a": "passed"}, test_hash="T1")
    _run(index, "r2", {"t.py::a": "failed"}, test_hash="T2")
    ev = single_evidence(index, "t.py::a", closure="C", test_hash="T2", env_key="E")
    assert ev.regression is True
    assert ev.test_changed_since_pass is True
    text = regression_instruction("t.py::a", "r1", True)
    assert text == ("plumb: regression: t.py::a passed in run r1 and now fails (test source "
                    "changed since the pass). Tell the owner, with a read-back, and ask how to "
                    "proceed.")
    assert "(test source" not in regression_instruction("t.py::a", "r1", False)


@pytest.mark.sr("SR-254")
def test_edited_test_that_passed_then_fails_is_regression(project: Path) -> None:
    first = open_verify(open_core(project)).run(nodes=["tests/test_helper.py"])
    assert first.ok
    node = "tests/test_helper.py::test_twice"
    write(project, "tests/test_helper.py",
          "from pkg.helper import twice\n\n\ndef test_twice():\n    assert twice(2) == 5\n")
    second = open_verify(open_core(project)).run(nodes=["tests/test_helper.py"])
    assert second.failed == [node]
    assert second.regressions == [{"node": node, "passed_in": first.run_id,
                                   "test_changed_since_pass": True}]
    ev = open_verify(open_core(project)).evidence([node])[node]
    assert ev.state == "fresh-fail"
    assert ev.regression is True and ev.test_changed_since_pass is True


@pytest.mark.sr("SR-254")
def test_new_red_test_is_not_regression(project: Path) -> None:
    write(project, "tests/test_new.py", "def test_red():\n    assert False\n")
    report = open_verify(open_core(project)).run(nodes=["tests/test_new.py"])
    assert report.failed == ["tests/test_new.py::test_red"]
    assert report.regressions == []
    assert report.not_yet_passing == ["tests/test_new.py::test_red"]
    ev = open_verify(open_core(project)).evidence(["tests/test_new.py::test_red"])
    assert ev["tests/test_new.py::test_red"].regression is False


@pytest.mark.sr("SR-254")
def test_collection_error_of_passing_test_is_regression(project: Path) -> None:
    first = open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert first.ok
    write(project, "src/pkg/mod.py", "def plus(a, b):\n    return a + b\n")
    second = open_verify(open_core(project)).run(changed=["src/pkg/mod.py"])
    assert "tests/test_mod.py" in second.collection_errors
    assert second.outcomes["tests/test_mod.py::test_add"] == "failed"
    assert second.outcomes["tests/test_mod.py::test_add_zero"] == "failed"
    assert [r["node"] for r in second.regressions] == ["tests/test_mod.py::test_add",
                                                       "tests/test_mod.py::test_add_zero"]
    assert all(r["passed_in"] == first.run_id for r in second.regressions)
    # test_twice never passed: a collection error there is not yet passing, not a regression
    assert second.not_yet_passing == ["tests/test_helper.py::test_twice"]
    node = "tests/test_mod.py::test_add"
    ev = open_verify(open_core(project)).evidence([node, "tests/test_mod.py"])
    assert ev[node].state == "fresh-fail" and ev[node].regression is True
    assert ev["tests/test_mod.py"].regression is True


@pytest.mark.sr("SR-254")
def test_collection_error_marks_only_selected_nodes(project: Path) -> None:
    first = open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert first.ok
    write(project, "src/pkg/mod.py", "def plus(a, b):\n    return a + b\n")
    second = open_verify(open_core(project)).run(nodes=["tests/test_mod.py::test_add"])
    assert second.outcomes == {"tests/test_mod.py::test_add": "failed"}
    assert [r["node"] for r in second.regressions] == ["tests/test_mod.py::test_add"]
