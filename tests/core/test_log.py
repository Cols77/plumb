"""K3: append-only, hash-chained logs (spec 5.7), one file per entry (SP6 6)."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

import pytest
from logutil import entries as log_entries
from logutil import entry_files, legacy_entry, tamper, write_legacy

from plumb import log
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-006")


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlumbPaths:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


def test_append_chains_prev_digest(paths: PlumbPaths) -> None:
    first = log.append(paths, "events", "repin", {"a": 1})
    second = log.append(paths, "events", "approval", {"b": 2})
    assert first.prev is None
    assert second.prev == first.digest
    assert first.digest.startswith("sha256:")
    raw = log_entries(paths.root, "events")
    assert [r["kind"] for r in raw] == ["repin", "approval"]
    assert raw[1]["prev"] == raw[0]["digest"]
    on_disk = json.loads((paths.log_dir / first.name).read_text(encoding="utf-8"))
    assert set(on_disk) == {"v", "kind", "at", "marker", "payload", "prev", "digest"}
    assert log.verify_chain(paths, "events") == []


def test_digest_detects_modified_line(paths: PlumbPaths) -> None:
    log.append(paths, "events", "approval", {"records": [{"id": "SR-001"}]})
    log.append(paths, "events", "repin", {})
    name = tamper(paths.root, "events", 0, lambda t: t.replace("SR-001", "SR-002"))
    problems = log.verify_chain(paths, "events")
    assert any("digest" in p and p.startswith(name) for p in problems)


def test_missing_prev_detected(paths: PlumbPaths) -> None:
    entries = [log.append(paths, "events", "repin", {"i": i}) for i in range(3)]
    (paths.log_dir / entries[1].name).unlink()
    problems = log.verify_chain(paths, "events")
    assert any("prev" in p and p.startswith(entries[2].name) for p in problems)


def test_reordered_legacy_lines_detected(paths: PlumbPaths) -> None:
    first = legacy_entry("repin", {"i": 0}, None)
    second = legacy_entry("repin", {"i": 1}, first["digest"])
    third = legacy_entry("repin", {"i": 2}, second["digest"])
    write_legacy(paths.root, "events", [second, first, third])
    assert log.verify_chain(paths, "events")


def test_union_merged_fork_accepted(paths: PlumbPaths, tmp_path: Path) -> None:
    """Two branches that each appended: their entry files sit side by side after the merge,
    the chain forks, and every prev still resolves."""
    log.append(paths, "events", "repin", {"base": True})
    base_files = set(entry_files(paths.root))
    snapshot = tmp_path / "base-log"
    shutil.copytree(paths.log_dir, snapshot)
    branch_a = log.append(paths, "events", "repin", {"branch": "a"})
    a_file = (paths.log_dir / branch_a.name).read_bytes()
    shutil.rmtree(paths.log_dir)
    shutil.copytree(snapshot, paths.log_dir)
    paths.log_head.unlink()
    branch_b = log.append(paths, "events", "repin", {"branch": "b"})
    (paths.log_dir / branch_a.name).write_bytes(a_file)  # the merge brings a's file
    assert branch_a.prev == branch_b.prev
    assert set(entry_files(paths.root)) == base_files | {branch_a.name, branch_b.name}
    assert log.verify_chain(paths, "events") == []
    after = log.append(paths, "events", "repin", {"after": True})
    assert after.prev == branch_b.digest
    assert log.verify_chain(paths, "events") == []


def test_concurrent_appends_do_not_interleave(paths: PlumbPaths) -> None:
    def worker(n: int) -> None:
        for i in range(10):
            log.append(paths, "events", "repin", {"worker": n, "i": i, "pad": "x" * 200})

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    entries = log_entries(paths.root, "events")
    assert len(entries) == 40 and len(entry_files(paths.root)) == 40
    assert log.verify_chain(paths, "events") == []
    digests = [e["digest"] for e in entries]
    assert [e["prev"] for e in entries[1:]] == digests[:-1]
    assert not paths.lock.exists()


def test_read_kinds_streams_and_legacy_offset(paths: PlumbPaths) -> None:
    log.append(paths, "events", "repin", {"i": 0})
    log.append(paths, "events", "approval", {"i": 1})
    log.append(paths, "evidence", "test-run", {"i": 2})
    entries = list(log.read(paths, "events"))
    assert [e.payload["i"] for e in entries] == [0, 1]
    assert all(e.offset == -1 and e.name for e in entries)
    assert [e.kind for e in log.read(paths, "events", kinds=["approval"])] == ["approval"]
    assert [e.stream for e in log.read(paths, "evidence")] == ["evidence"]
    assert list(log.read(PlumbPaths(paths.root / "nowhere"), "events")) == []
    # legacy lines keep their byte offsets for since_offset during the transition
    shutil.rmtree(paths.log_dir)
    one = legacy_entry("repin", {"i": 0}, None)
    two = legacy_entry("approval", {"i": 1}, one["digest"])
    write_legacy(paths.root, "events", [one, two])
    legacy = list(log.read(paths, "events"))
    assert legacy[0].offset == 0 and legacy[1].offset > 0
    assert legacy[1].name == "events.jsonl:2"
    assert [e.payload["i"] for e in log.read(paths, "events",
                                             since_offset=legacy[1].offset)] == [1]


def test_marker_recorded(paths: PlumbPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    assert log.append(paths, "events", "repin", {}).marker == "none"
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    assert log.append(paths, "events", "repin", {}).marker == "claude-code"
    assert log_entries(paths.root, "events")[1]["marker"] == "claude-code"


def test_stale_lock_is_removed(paths: PlumbPaths) -> None:
    import os
    import time

    paths.cache.mkdir(parents=True, exist_ok=True)
    paths.lock.write_text("stale", encoding="utf-8")
    old = time.time() - 60
    os.utime(paths.lock, (old, old))
    log.append(paths, "events", "repin", {})
    assert not paths.lock.exists()
