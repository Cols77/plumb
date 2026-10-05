"""K3: append-only, hash-chained JSONL logs (spec 5.7)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from plumb import log
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-006")


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlumbPaths:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_append_chains_prev_digest(paths: PlumbPaths) -> None:
    first = log.append(paths, "events", "repin", {"a": 1})
    second = log.append(paths, "events", "approval", {"b": 2})
    assert first.prev is None
    assert second.prev == first.digest
    assert first.digest.startswith("sha256:")
    raw = _lines(paths.log_events)
    assert [r["kind"] for r in raw] == ["repin", "approval"]
    assert raw[1]["prev"] == raw[0]["digest"]
    assert set(raw[0]) == {"v", "kind", "at", "marker", "payload", "prev", "digest"}
    assert log.verify_chain(paths, "events") == []


def test_digest_detects_modified_line(paths: PlumbPaths) -> None:
    log.append(paths, "events", "approval", {"records": [{"id": "SR-001"}]})
    log.append(paths, "events", "repin", {})
    text = paths.log_events.read_text(encoding="utf-8").replace("SR-001", "SR-002")
    paths.log_events.write_text(text, encoding="utf-8")
    problems = log.verify_chain(paths, "events")
    assert any("digest" in p and "line 1" in p for p in problems)


def test_missing_prev_detected(paths: PlumbPaths) -> None:
    for i in range(3):
        log.append(paths, "events", "repin", {"i": i})
    lines = paths.log_events.read_text(encoding="utf-8").splitlines(keepends=True)
    paths.log_events.write_text(lines[0] + lines[2], encoding="utf-8")
    problems = log.verify_chain(paths, "events")
    assert any("prev" in p and "line 2" in p for p in problems)


def test_reordered_lines_detected(paths: PlumbPaths) -> None:
    for i in range(3):
        log.append(paths, "events", "repin", {"i": i})
    lines = paths.log_events.read_text(encoding="utf-8").splitlines(keepends=True)
    paths.log_events.write_text(lines[1] + lines[0] + lines[2], encoding="utf-8")
    assert log.verify_chain(paths, "events")


def test_union_merged_fork_accepted(paths: PlumbPaths, tmp_path: Path) -> None:
    log.append(paths, "events", "repin", {"base": True})
    base = paths.log_events.read_bytes()
    log.append(paths, "events", "repin", {"branch": "a"})
    branch_a = paths.log_events.read_bytes()[len(base):]
    paths.log_events.write_bytes(base)
    log.append(paths, "events", "repin", {"branch": "b"})
    branch_b = paths.log_events.read_bytes()[len(base):]
    paths.log_events.write_bytes(base + branch_a + branch_b)
    assert log.verify_chain(paths, "events") == []
    after = log.append(paths, "events", "repin", {"after": True})
    assert after.prev == json.loads(branch_b)["digest"]
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
    entries = _lines(paths.log_events)
    assert len(entries) == 40
    assert log.verify_chain(paths, "events") == []
    digests = [e["digest"] for e in entries]
    assert [e["prev"] for e in entries[1:]] == digests[:-1]
    assert not paths.lock.exists()


def test_read_since_offset(paths: PlumbPaths) -> None:
    log.append(paths, "events", "repin", {"i": 0})
    log.append(paths, "events", "approval", {"i": 1})
    log.append(paths, "evidence", "test-run", {"i": 2})
    entries = list(log.read(paths, "events"))
    assert [e.payload["i"] for e in entries] == [0, 1]
    assert entries[0].offset == 0 and entries[1].offset > 0
    assert [e.payload["i"] for e in log.read(paths, "events", since_offset=entries[1].offset)] \
        == [1]
    assert [e.kind for e in log.read(paths, "events", kinds=["approval"])] == ["approval"]
    assert [e.stream for e in log.read(paths, "evidence")] == ["evidence"]
    assert list(log.read(PlumbPaths(paths.root / "nowhere"), "events")) == []


def test_marker_recorded(paths: PlumbPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    assert log.append(paths, "events", "repin", {}).marker == "none"
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    assert log.append(paths, "events", "repin", {}).marker == "claude-code"
    assert _lines(paths.log_events)[1]["marker"] == "claude-code"


def test_stale_lock_is_removed(paths: PlumbPaths) -> None:
    import os
    import time

    paths.cache.mkdir(parents=True, exist_ok=True)
    paths.lock.write_text("stale", encoding="utf-8")
    old = time.time() - 60
    os.utime(paths.lock, (old, old))
    log.append(paths, "events", "repin", {})
    assert not paths.lock.exists()
