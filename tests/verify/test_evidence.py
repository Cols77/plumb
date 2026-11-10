"""V5: evidence pinned to tree, closure, test source and env key (spec 7.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git
from verify_helpers import commit_all, make_project, write

from iaso.api import open_core
from iaso.verify import envid, open_verify
from iaso.verify.evidence import apply_entry, load_index, payload_checksum, single_evidence


@pytest.fixture
def project(repo: Path) -> Path:
    make_project(repo)
    commit_all(repo)
    return repo


def _entries(root: Path) -> list[dict]:
    from logutil import entries

    return entries(root, "evidence")


@pytest.mark.sr("SR-255")
def test_run_appends_test_run_entry_with_tree_and_env(project: Path) -> None:
    report = open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert report.ok
    entry = _entries(project)[-1]
    assert entry["kind"] == "test-run"
    payload = entry["payload"]
    assert payload["run_id"] == report.run_id
    assert payload["tree"]["head"] == git(project, "rev-parse", "HEAD").strip()
    assert payload["tree"]["head_tree"] == git(project, "rev-parse", "HEAD^{tree}").strip()
    assert payload["tree"]["dirty"].startswith("sha256:")
    assert payload["env"]["env_key"] == envid.env_key(project)
    assert "identity" in payload["env"]  # VS3: null when the environment is unknown
    ids = {n["id"]: n for n in payload["nodes"]}
    assert set(ids) == {"tests/test_mod.py::test_add", "tests/test_mod.py::test_add_zero"}
    node = ids["tests/test_mod.py::test_add"]
    assert node["outcome"] == "passed"
    assert node["closure"].startswith("sha256:") and node["test_hash"].startswith("sha256:")
    assert payload["self"] == payload_checksum(payload)


@pytest.mark.sr("SR-255")
def test_fresh_pass_requires_matching_closure_test_and_env_key(project: Path) -> None:
    open_verify(open_core(project)).run(nodes=["tests/test_helper.py"])
    node = "tests/test_helper.py::test_twice"
    ev = open_verify(open_core(project)).evidence([node, "tests/test_helper.py"])
    assert ev[node].state == "fresh-pass"
    assert ev["tests/test_helper.py"].state == "fresh-pass"
    write(project, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    ev = open_verify(open_core(project)).evidence([node, "tests/test_mod.py"])
    assert ev[node].state == "stale"
    assert ev[node].reuse_miss == "closure"
    assert ev["tests/test_mod.py"].state == "none"


@pytest.mark.sr("SR-255")
def test_reuse_miss_names_differing_part() -> None:
    index = {"nodes": {}, "full": None}
    apply_entry(index, {"run_id": "r1", "env": {"env_key": "E"},
                        "nodes": [{"id": "t.py::a", "outcome": "passed", "closure": "C",
                                   "test_hash": "T"}]})
    fresh = single_evidence(index, "t.py::a", closure="C", test_hash="T", env_key="E")
    assert (fresh.state, fresh.reuse_miss) == ("fresh-pass", None)
    for kwargs, miss in (({"closure": "C", "test_hash": "T2", "env_key": "E"}, "test"),
                         ({"closure": "C2", "test_hash": "T", "env_key": "E"}, "closure"),
                         ({"closure": "C", "test_hash": "T", "env_key": "E2"}, "env")):
        got = single_evidence(index, "t.py::a", **kwargs)
        assert (got.state, got.reuse_miss) == ("stale", miss)
    apply_entry(index, {"run_id": "r2", "discarded": "inputs changed", "env": {"env_key": "E"},
                        "nodes": [{"id": "t.py::a", "outcome": "failed", "closure": "C",
                                   "test_hash": "T"}]})
    assert single_evidence(index, "t.py::a", closure="C", test_hash="T",
                           env_key="E").state == "fresh-pass"


@pytest.mark.sr("SR-255")
def test_observed_run_time_scales_the_estimates() -> None:
    """Each run's wall clock against its estimate adapts the budget fill (VS2)."""
    index = {"v": 1, "offset": 0, "prefix": None, "nodes": {}, "full": None, "removed": {}}
    apply_entry(index, {"run_id": "r1", "nodes": [],
                        "timing": {"expected_s": 10.0, "elapsed_s": 15.0}})
    assert index["scale"] == 1.25  # halfway from 1.0 to the observed 1.5
    # a timeout is a lower bound: the scale rises to it at once
    apply_entry(index, {"run_id": "r2", "nodes": [], "timeout": True,
                        "timing": {"expected_s": 14.6, "elapsed_s": 22.5}})
    assert index["scale"] == pytest.approx(22.5 / 14.6, abs=1e-3)
    # a short run is mostly start-up time: it teaches nothing
    before = index["scale"]
    apply_entry(index, {"run_id": "r3", "nodes": [],
                        "timing": {"expected_s": 0.5, "elapsed_s": 3.0}})
    assert index["scale"] == before
    # a discarded run teaches nothing; the scale is capped
    apply_entry(index, {"run_id": "r4", "nodes": [], "discarded": "inputs changed",
                        "timing": {"expected_s": 10.0, "elapsed_s": 100.0}})
    assert index["scale"] == before
    apply_entry(index, {"run_id": "r5", "nodes": [], "timeout": True,
                        "timing": {"expected_s": 0.05, "elapsed_s": 8.0}})
    assert index["scale"] == 3.0


@pytest.mark.sr("SR-255")
def test_index_rebuilt_from_log_after_cache_delete(repo: Path) -> None:
    core = open_core(repo)
    for run_id, outcome in (("r1", "passed"), ("r2", "failed")):
        core.log_append("evidence", "test-run", {
            "run_id": run_id, "env": {"env_key": "E"},
            "nodes": [{"id": "t.py::a", "outcome": outcome, "closure": "C", "test_hash": "T"}]})
    first = load_index(open_core(repo))
    cache = repo / ".iaso" / "cache" / "evidence_index.json"
    assert cache.exists()
    cache.unlink()
    again = load_index(open_core(repo))
    assert again["nodes"] == first["nodes"]
    assert again["nodes"]["t.py::a"]["last"]["run_id"] == "r2"
    assert again["nodes"]["t.py::a"]["last_pass"]["run_id"] == "r1"
    core.log_append("evidence", "test-run", {
        "run_id": "r3", "env": {"env_key": "E"},
        "nodes": [{"id": "t.py::a", "outcome": "passed", "closure": "C", "test_hash": "T"}]})
    assert load_index(open_core(repo))["nodes"]["t.py::a"]["last"]["run_id"] == "r3"


@pytest.mark.sr("SR-255")
def test_env_key_changes_with_lock_and_python(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    base = envid.env_key(tmp_path)
    (tmp_path / "uv.lock").write_bytes(b"version = 1\n")
    with_lock = envid.env_key(tmp_path)
    assert with_lock != base
    (tmp_path / "uv.lock").write_bytes(b"version = 1\r\n")
    assert envid.env_key(tmp_path) == with_lock
    monkeypatch.setattr(envid, "python_version", lambda: "CPython 9.9.9")
    assert envid.env_key(tmp_path) != with_lock


@pytest.mark.sr("SR-255")
def test_full_pending_cleared_by_full_run_evidence(project: Path) -> None:
    assert open_verify(open_core(project)).full_pending().pending is True
    report = open_verify(open_core(project)).run(full=True)
    assert report.ok, report.as_dict()
    pending = open_verify(open_core(project)).full_pending()
    assert pending.pending is False, pending.reasons
    write(project, "pyproject.toml",
          (project / "pyproject.toml").read_text(encoding="utf-8") + "# edited\n")
    pending = open_verify(open_core(project)).full_pending()
    assert pending.reasons == ("pyproject.toml changed",)
    write(project, "src/pkg/orphan.py", "X = 1\n")
    pending = open_verify(open_core(project)).full_pending()
    assert "src/pkg/orphan.py has no covering test" in pending.reasons


class _Map:
    """The slice of the test map ``node_evidence`` reads."""
    files = {"t.py": {"nodes": {"t.py::test_p": 1}}}

    def closure_hash(self, f): return "C"
    def node_hash(self, n): return "T"
    def nodes_of(self, f): return ["t.py::test_p"]


@pytest.mark.sr("SR-352")
def test_a_parameter_dropped_from_a_later_run_does_not_keep_the_test_failing() -> None:
    from iaso.verify.evidence import node_evidence

    index = {"v": 0, "nodes": {}}
    for run, outcomes in (("1", {"t.py::test_p[a]": "passed", "t.py::test_p[old]": "passed"}),
                          ("2", {"t.py::test_p[a]": "failed", "t.py::test_p[old]": "failed"}),
                          ("3", {"t.py::test_p[a]": "passed"})):  # [old] is gone from the file
        apply_entry(index, {"run_id": run, "env": {"env_key": "E", "identity": "I"},
                            "nodes": [{"id": n, "outcome": o, "closure": "C", "test_hash": "T"}
                                      for n, o in outcomes.items()]})
    for ref in ("t.py", "t.py::test_p"):
        ev = node_evidence(index, _Map(), ref, "E", "I")
        assert (ev.state, ev.last_failed, ev.regression) == ("fresh-pass", False, False), ref


@pytest.mark.sr("SR-352")
def test_a_parameter_a_later_run_no_longer_has_is_not_a_merge_regression(project: Path) -> None:
    """report-0e66c6ff: an old parameter of a test that still exists passed, then failed;
    a later run of the test no longer has it: it holds no merge."""
    core = open_core(project)
    node = "tests/test_mod.py::test_add"
    for run_id, nodes in (("20261001T000000Z-a", {f"{node}[old]": "passed"}),
                          ("20261002T000000Z-b", {f"{node}[old]": "failed"})):
        core.log_append("evidence", "test-run", {
            "run_id": run_id, "env": {"env_key": "E"},
            "nodes": [{"id": n, "outcome": o, "closure": "C", "test_hash": "T"}
                      for n, o in nodes.items()]})
    assert open_verify(open_core(project)).unresolved_regressions() == [f"{node}[old]"]
    open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert open_verify(open_core(project)).unresolved_regressions() == []


@pytest.mark.sr("SR-352")
def test_a_test_parametrized_since_its_failure_does_not_keep_the_test_failing() -> None:
    """The bare id a test had before it was parametrized: the newest run of its family wins,
    whether the file, the family or the bare id is asked for."""
    from iaso.verify.evidence import node_evidence

    index = {"v": 0, "nodes": {}}
    for run, outcomes in (("1", {"t.py::test_p": "failed"}),   # before parametrize
                          ("2", {"t.py::test_p[a]": "passed", "t.py::test_p[b]": "passed"})):
        apply_entry(index, {"run_id": run, "env": {"env_key": "E", "identity": "I"},
                            "nodes": [{"id": n, "outcome": o, "closure": "C", "test_hash": "T"}
                                      for n, o in outcomes.items()]})
    for ref in ("t.py", "t.py::test_p"):
        ev = node_evidence(index, _Map(), ref, "E", "I")
        assert (ev.state, ev.last_failed) == ("fresh-pass", False), ref
    assert node_evidence(index, _Map(), "t.py::test_p[a]", "E", "I").state == "fresh-pass"
