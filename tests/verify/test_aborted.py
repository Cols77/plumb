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


@pytest.mark.sr("SR-020")
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


@pytest.mark.sr("SR-020")
def test_aborted_full_run_never_satisfies_full_pending(project: Path) -> None:
    write(project, "tests/conftest.py", BROKEN_CONFTEST)
    report = open_verify(open_core(project)).run(full=True)
    assert report.ok is False
    assert report.aborted
    pending = open_verify(open_core(project)).full_pending()
    assert pending.pending is True


@pytest.mark.sr("SR-018")
def test_unknown_node_id_falls_back_to_its_file(project: Path) -> None:
    report = open_verify(open_core(project)).run(
        nodes=["tests/test_mod.py::test_renamed", "tests/test_helper.py"])
    assert report.aborted is None
    assert report.ok
    assert report.outcomes["tests/test_helper.py::test_twice"] == "passed"
    assert report.outcomes["tests/test_mod.py::test_add"] == "passed"
    assert report.selection is not None
    assert "tests/test_mod.py" in report.selection.nodes


@pytest.mark.sr("SR-018")
def test_index_rebuilds_when_log_prefix_changes(repo: Path) -> None:
    core = open_core(repo)

    def payload(run_id: str, node: str) -> dict:
        return {"run_id": run_id, "env": {"env_key": "E"},
                "nodes": [{"id": node, "outcome": "passed", "closure": "C", "test_hash": "T"}]}

    log = core.paths.log_evidence
    core.log_append("evidence", "test-run", payload("r-lane", "t.py::lane_own"))
    assert set(load_index(core)["nodes"]) == {"t.py::lane_own"}
    lane_line = log.read_bytes()
    core.log_append("evidence", "test-run", payload("r-a", "t.py::main_pass_a"))
    core.log_append("evidence", "test-run", payload("r-b", "t.py::main_pass_b"))
    main_lines = log.read_bytes()[len(lane_line):]
    log.write_bytes(main_lines + lane_line)  # a rebase puts main's lines first
    nodes = load_index(core)["nodes"]
    assert set(nodes) == {"t.py::lane_own", "t.py::main_pass_a", "t.py::main_pass_b"}
    cached = json.loads(core.paths.evidence_index.read_text(encoding="utf-8"))
    assert cached["offset"] == log.stat().st_size


@pytest.mark.sr("SR-017")
def test_cli_run_exits_nonzero_when_pytest_aborts(project: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    from plumb import cli

    write(project, "tests/conftest.py", BROKEN_CONFTEST)
    assert cli.main(["tests", "run", "--nodes", "tests/test_mod.py",
                     "--root", str(project)]) != 0
    assert "plumb: run aborted" in capsys.readouterr().out


@pytest.mark.sr("SR-018")
def test_runnable_targets_keep_known_ids_and_absorb_into_file(project: Path) -> None:
    verify = open_verify(open_core(project))
    assert verify.runnable_targets(["tests/test_mod.py::test_add",
                                    "tests/test_helper.py::test_gone"]) == [
        "tests/test_mod.py::test_add", "tests/test_helper.py"]
    assert verify.runnable_targets(["tests/test_mod.py::test_add[1]",
                                    "tests/test_mod.py::test_old",
                                    "tests/test_mod.py::test_add_zero"]) == ["tests/test_mod.py"]
