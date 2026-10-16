"""A pytest run that aborts or executes nothing is never a clean run (R3, R5, spec 7.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from plumb.api import open_core
from plumb.verify import open_verify
from plumb.verify.evidence import load_index

BROKEN_CONFTEST = "import does_not_exist_xyz\n"


@pytest.fixture
def project(repo: Path) -> Path:
    make_project(repo)
    commit_all(repo)
    return repo


@pytest.mark.sr("SR-254")
def test_conftest_import_failure_turns_passes_into_regressions(project: Path) -> None:
    first = open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert first.ok
    write(project, "tests/conftest.py", BROKEN_CONFTEST)
    second = open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert second.ok is False
    assert second.aborted
    assert second.exit_status not in (0, 1)
    assert second.outcomes == {"tests/test_mod.py::test_add": "failed",
                               "tests/test_mod.py::test_add_zero": "failed"}
    assert [r["node"] for r in second.regressions] == ["tests/test_mod.py::test_add",
                                                       "tests/test_mod.py::test_add_zero"]
    node = "tests/test_mod.py::test_add"
    ev = open_verify(open_core(project)).evidence([node])
    assert ev[node].regression is True


@pytest.mark.sr("SR-254")
def test_aborted_full_run_never_satisfies_full_pending(project: Path) -> None:
    write(project, "tests/conftest.py", BROKEN_CONFTEST)
    report = open_verify(open_core(project)).run(full=True)
    assert report.ok is False
    assert report.aborted
    pending = open_verify(open_core(project)).full_pending()
    assert pending.pending is True


@pytest.mark.sr("SR-255")
def test_unknown_node_id_falls_back_to_its_file(project: Path) -> None:
    report = open_verify(open_core(project)).run(
        nodes=["tests/test_mod.py::test_renamed", "tests/test_helper.py"])
    assert report.aborted is None
    assert report.ok
    assert report.outcomes["tests/test_helper.py::test_twice"] == "passed"
    assert report.outcomes["tests/test_mod.py::test_add"] == "passed"
    assert report.selection is not None
    assert "tests/test_mod.py" in report.selection.nodes


@pytest.mark.sr("SR-255")
def test_index_rebuilds_when_log_prefix_changes(repo: Path) -> None:
    core = open_core(repo)

    def payload(run_id: str, node: str) -> dict:
        return {"run_id": run_id, "env": {"env_key": "E"},
                "nodes": [{"id": node, "outcome": "passed", "closure": "C", "test_hash": "T"}]}

    # legacy JSONL lines (readers accept them until the migration, SP6 6.3)
    from logutil import legacy_entry, write_legacy

    log = core.paths.log_evidence
    lane = legacy_entry("test-run", payload("r-lane", "t.py::lane_own"), None,
                        at="2026-10-05T12:00:03Z")
    write_legacy(repo, "evidence", [lane])
    assert set(load_index(core)["nodes"]) == {"t.py::lane_own"}
    a = legacy_entry("test-run", payload("r-a", "t.py::main_pass_a"), None,
                     at="2026-10-05T12:00:01Z")
    b = legacy_entry("test-run", payload("r-b", "t.py::main_pass_b"), a["digest"],
                     at="2026-10-05T12:00:02Z")
    log.write_bytes(b"")
    write_legacy(repo, "evidence", [a, b, lane])  # a rebase puts main's lines first
    nodes = load_index(core)["nodes"]
    assert set(nodes) == {"t.py::lane_own", "t.py::main_pass_a", "t.py::main_pass_b"}
    cached = json.loads(core.paths.evidence_index.read_text(encoding="utf-8"))
    assert cached["applied"] == [a["digest"], b["digest"], lane["digest"]]


@pytest.mark.sr("SR-255")
def test_cli_run_exits_nonzero_when_pytest_aborts(project: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    from plumb import cli

    write(project, "tests/conftest.py", BROKEN_CONFTEST)
    assert cli.main(["tests", "run", "--nodes", "tests/test_mod.py",
                     "--root", str(project)]) != 0
    assert "plumb: run aborted" in capsys.readouterr().out


@pytest.mark.sr("SR-255")
def test_runnable_targets_keep_known_ids_and_absorb_into_file(project: Path) -> None:
    verify = open_verify(open_core(project))
    assert verify.runnable_targets(["tests/test_mod.py::test_add",
                                    "tests/test_helper.py::test_gone"]) == [
        "tests/test_mod.py::test_add", "tests/test_helper.py"]
    assert verify.runnable_targets(["tests/test_mod.py::test_add[1]",
                                    "tests/test_mod.py::test_old",
                                    "tests/test_mod.py::test_add_zero"]) == ["tests/test_mod.py"]


@pytest.mark.sr("SR-254")
@pytest.mark.parametrize("payload", [
    {"exit_status": 5, "nodes": []},  # nothing collected
    {"exit_status": 1, "collection_errors": ["tests/test_x.py"],
     "nodes": [{"id": "tests/test_a.py::test_a", "outcome": "passed"}]},
    {"exit_status": 0, "nodes": []},  # nothing ran
], ids=["exit-5", "collection-error", "no-nodes"])
def test_full_run_without_a_clean_collection_never_clears_full_pending(payload) -> None:
    from plumb.verify.evidence import apply_entry

    index = {"nodes": {}, "full": None}
    apply_entry(index, {"run_id": "r1", "full": True, "env": {"env_key": "E"},
                        "infra": {}, "files": {}, **payload})
    assert index["full"] is None


@pytest.mark.sr("SR-254")
def test_full_run_that_collects_nothing_from_known_tests_is_aborted(project: Path) -> None:
    write(project, "pytest.ini", "[pytest]\ntestpaths = nowhere\npython_files = nope_*.py\n")
    report = open_verify(open_core(project)).run(full=True)
    assert report.exit_status == 5
    assert report.ok is False
    assert open_verify(open_core(project)).full_pending().pending is True
