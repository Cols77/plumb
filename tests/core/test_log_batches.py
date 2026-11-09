"""Real file I/O bounds and recovery for worker log writes (SR-153)."""

import json
import os
from pathlib import Path

import pytest

from iaso import log
from iaso.api import Core
from iaso.paths import IasoPaths

pytestmark = pytest.mark.sr("SR-232")


def io_counts(monkeypatch, paths):
    counts = {"reads": 0, "heads": 0, "locks": 0}
    read, replace, open_ = Path.read_text, os.replace, os.open

    def reading(path, *args, **kwargs):
        if path == paths.log_head:
            counts["reads"] += 1
        return read(path, *args, **kwargs)

    def replacing(src, dst, *args, **kwargs):
        if Path(dst) == paths.log_head:
            counts["heads"] += 1
        return replace(src, dst, *args, **kwargs)

    def opening(path, flags, *args, **kwargs):
        if Path(path) == paths.lock and flags & os.O_EXCL:
            counts["locks"] += 1
        return open_(path, flags, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reading)
    monkeypatch.setattr(os, "replace", replacing)
    monkeypatch.setattr(os, "open", opening)
    return counts


def test_single_append_reads_head_once_and_preserves_other_stream(tmp_path, monkeypatch):
    paths = IasoPaths(tmp_path)
    first = log.append(paths, "evidence", "test-run", {})
    counts = io_counts(monkeypatch, paths)
    log.append(paths, "events", "note", {})
    assert counts == {"reads": 1, "heads": 1, "locks": 1}
    assert json.loads(paths.log_head.read_text())["evidence"]["digest"] == first.digest



@pytest.mark.parametrize("entries,exception", [
    ([("note", {}), ("../bad", {})], ValueError),
    ([("note", {}), ("test-run", {})], ValueError),
    ([("note", {}), ("note", {"bad": {1: "x", "mixed": "keys"}})], TypeError),
    ([("note", {}), ("approval", {"by": "owner-words"})], log.LogError),
])
def test_batch_validates_every_entry_before_any_write(tmp_path, monkeypatch, entries, exception):
    monkeypatch.delenv("IASO_WORKER", raising=False)
    paths = IasoPaths(tmp_path)
    with pytest.raises(exception):
        log.append_many(paths, "events", [("note", {})] * 33 + entries)
    assert list(log.read(paths, "events")) == []
    assert not paths.log_head.exists()


def test_partial_batch_invalidates_head_and_core_events_before_recovery(tmp_path, monkeypatch):
    core = Core(tmp_path)
    core.log_append("events", "note", {"i": 0})
    assert len(core.events()) == 1
    write = log._write_new
    persisted = []

    def interrupted(*args, **kwargs):
        name = write(*args, **kwargs)
        persisted.append(name)
        if len(persisted) == 2:
            raise OSError("interrupted after persistence")
        return name

    with monkeypatch.context() as patch:
        patch.setattr(log, "_write_new", interrupted)
        with pytest.raises(OSError, match="interrupted"):
            core.log_append_many("events", [("note", {"i": i}) for i in range(1, 4)])
    assert not core.paths.log_head.exists()
    assert [e.payload["i"] for e in core.events()] == [0, 1, 2]
    recovered = core.log_append("events", "note", {"i": 4})
    assert recovered.prev == core.events()[-2].digest
    assert log.verify_chain(core.paths, "events") == []


def test_failed_head_invalidation_prevents_persistence(tmp_path, monkeypatch):
    paths = IasoPaths(tmp_path)
    first = log.append(paths, "events", "note", {})
    unlink = Path.unlink

    def denied(path, *args, **kwargs):
        if path == paths.log_head:
            raise PermissionError("head busy")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(PermissionError, match="head busy"):
        log.append_many(paths, "events", [("note", {"next": True})])
    assert [e.digest for e in log.read(paths, "events")] == [first.digest]


def test_failed_head_publication_rebuilds_chain(tmp_path, monkeypatch):
    paths = IasoPaths(tmp_path)
    log.append(paths, "events", "note", {})
    replace = os.replace

    def denied(src, dst, *args, **kwargs):
        if Path(dst) == paths.log_head:
            raise PermissionError("head busy")
        return replace(src, dst, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", denied)
        batch = log.append_many(paths, "events", [("note", {"i": 1}), ("note", {"i": 2})])
    assert not paths.log_head.exists()
    assert log.append(paths, "events", "note", {}).prev == batch[-1].digest
    assert log.verify_chain(paths, "events") == []


def test_empty_batch_does_no_io_and_unknown_stream_is_rejected(tmp_path, monkeypatch):
    paths = IasoPaths(tmp_path)
    counts = io_counts(monkeypatch, paths)
    assert log.append_many(paths, "events", []) == []
    with pytest.raises(ValueError, match="unknown log stream"):
        log.append_many(paths, "unknown", [])
    assert counts == {"reads": 0, "heads": 0, "locks": 0}


def test_concurrent_batches_form_one_chain(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    paths = IasoPaths(tmp_path)

    def append_batch(n):
        return log.append_many(paths, "events", [("note", {"batch": n, "i": i})
                                                for i in range(6)])

    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(pool.map(append_batch, range(3)))
    entries = list(log.read(paths, "events"))
    assert len(entries) == sum(map(len, batches)) == 18
    assert [e.prev for e in entries[1:]] == [e.digest for e in entries[:-1]]
    assert log.verify_chain(paths, "events") == []


def test_worker_writes_mixed_streams_and_notes_with_fresh_core_events(tmp_path, monkeypatch):
    from iaso.contracts import Applied
    from iaso.understand import worker

    core = Core(tmp_path)
    assert core.events() == []
    counts = io_counts(monkeypatch, core.paths)
    worker._write_applied(core, "s1", Applied(entries=(
        {"kind": "note", "payload": {"i": 1}},
        {"kind": "note", "payload": {"i": 2}},
        {"kind": "test-run", "payload": {"i": 3}},
        {"kind": "note", "payload": {"i": 4}},
    ), notes=("finished",)))
    assert counts == {"reads": 4, "heads": 4, "locks": 4}
    assert [e.payload["i"] for e in core.events() if e.kind == "note"] == [1, 2, 4]
    worker._note(core, "worker", "job", "another note")
    assert len(core.events()) == 5
    assert core.events()[-1].payload["detail"] == "another note"
    assert log.verify_chain(core.paths, "events") == []
    assert log.verify_chain(core.paths, "evidence") == []
