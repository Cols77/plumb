"""SP6 6.3, 6.4: the merge-boundary log check and the evidence index (SR-073, SR-074)."""

from __future__ import annotations

from pathlib import Path

import pytest
from logutil import delete, legacy_entry, tamper, write_legacy

from logs.gitrepo import commit_all, make_repo, run_git
from plumb import log
from plumb.api import open_core
from plumb.merge import log_integrity
from plumb.normalize import canonical_json
from plumb.verify.evidence import load_index


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    return make_repo(tmp_path / "r")


def _forked(root: Path) -> str:
    core = open_core(root)
    core.log_append("events", "mod-hello", {"i": 0})
    core.log_append("events", "approval", {"records": [{"id": "SR-001", "hash": "h"}]})
    commit_all(root, "base entries")
    run_git(root, "branch", "trunk")
    run_git(root, "checkout", "-q", "-b", "feat")
    return "trunk"


@pytest.mark.sr("SR-232")
def test_modified_entry_file_since_fork_reported(root: Path) -> None:
    base = _forked(root)
    name = tamper(root, "events", -1, lambda t: t.replace("SR-001", "SR-002"))
    problems, digests = log_integrity(open_core(root), base)
    assert any(p.startswith(f".plumb/log/{name}: entry modified since merge-base")
               for p in problems), problems
    open_core(root).log_append("events", "mod-hello", {"new": True})  # an addition is fine
    commit_all(root, "tamper committed")
    problems, _ = log_integrity(open_core(root), base)
    assert len(problems) == 1 and name in problems[0]


@pytest.mark.sr("SR-232")
def test_deleted_entry_file_since_fork_reported(root: Path) -> None:
    base = _forked(root)
    name = delete(root, "events", 0)
    problems, digests = log_integrity(open_core(root), base)
    assert problems == [f".plumb/log/{name}: entry deleted since merge-base "
                        f"{run_git(root, 'merge-base', base, 'HEAD').stdout.strip()[:12]}"]
    assert len(digests["events"]) == 1  # the surviving entry present at the fork


def _untracked(root: Path, kind: str) -> str:
    """Track one entry of ``kind`` (forced past the ignore), fork, then drop it from git only."""
    core = open_core(root)
    core.log_append("events", kind, {"i": 1})
    run_git(root, "add", "-f", "-A")
    run_git(root, "commit", "-q", "--no-verify", "-m", "tracked")
    run_git(root, "branch", "trunk")
    run_git(root, "checkout", "-q", "-b", "feat")
    run_git(root, "rm", "-q", "-r", "--cached", f".plumb/log/{kind}")
    run_git(root, "commit", "-q", "--no-verify", "-m", "stop tracking")
    return "trunk"


@pytest.mark.sr("SR-323")
def test_owner_words_entries_untracked_since_fork_are_not_a_loss(root: Path) -> None:
    """DEC-116, DEC-412, SR-323 EX-3: the owner asked to stop tracking their words; the files
    stay on disk, so their removal from version control is intended."""
    base = _untracked(root, "question-answer")
    problems, _ = log_integrity(open_core(root), base)
    assert problems == []


@pytest.mark.sr("SR-323")
def test_shared_kind_untracked_since_fork_still_fails(root: Path) -> None:
    base = _untracked(root, "approval")
    problems, _ = log_integrity(open_core(root), base)
    assert len(problems) == 1 and "entry deleted since merge-base" in problems[0]


@pytest.mark.sr("SR-232")
def test_legacy_lines_at_fork_satisfied_by_migrated_entries(root: Path) -> None:
    first = legacy_entry("mod-hello", {"i": 0}, None)
    second = legacy_entry("approval", {"records": []}, first["digest"])
    write_legacy(root, "events", [first, second])
    commit_all(root, "legacy log")
    run_git(root, "branch", "trunk")
    run_git(root, "checkout", "-q", "-b", "feat")
    paths = open_core(root).paths
    report = log.migrate(paths, dry_run=False)
    assert report.refused == () and len(report.written) == 2
    commit_all(root, "migrate")
    problems, digests = log_integrity(open_core(root), "trunk")
    assert problems == []
    assert digests["events"] == {first["digest"], second["digest"]}
    # a migrated file whose content was changed does not stand in for the line
    target = paths.log_dir / report.written[1]
    target.write_text(target.read_text(encoding="utf-8").replace('"records":[]',
                                                                 '"records":[1]'),
                      encoding="utf-8")
    problems, _ = log_integrity(open_core(root), "trunk")
    assert any("events.jsonl: line 2 at merge-base" in p for p in problems), problems


@pytest.mark.sr("SR-232")
def test_evidence_index_rebuilds_on_out_of_order_entry(root: Path) -> None:
    core = open_core(root)

    def payload(run_id: str, node: str) -> dict:
        return {"run_id": run_id, "env": {"env_key": "E"},
                "nodes": [{"id": node, "outcome": "passed", "closure": "C", "test_hash": "T"}]}

    mine = core.log_append("evidence", "test-run", payload("r-mine", "t.py::mine"))
    assert set(load_index(open_core(root))["nodes"]) == {"t.py::mine"}
    # unchanged stream: the index answers without reading the log
    assert set(load_index(open_core(root))["nodes"]) == {"t.py::mine"}
    # a merge brings an older run from another branch: it sorts before the last applied
    other = legacy_entry("test-run", payload("r-other", "t.py::other"), None,
                         at="2000-01-01T00:00:00Z")
    directory = core.paths.log_kind_dir("test-run")
    (directory / log.migrated_name(other)).write_bytes(canonical_json(other) + b"\n")
    index = load_index(open_core(root))
    assert set(index["nodes"]) == {"t.py::mine", "t.py::other"}
    assert index["applied"] == [other["digest"], mine.digest]
    # an applied entry vanished (a branch switch): rebuilt without it
    (directory / log.migrated_name(other)).unlink()
    assert set(load_index(open_core(root))["nodes"]) == {"t.py::mine"}
