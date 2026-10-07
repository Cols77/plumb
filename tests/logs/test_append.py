"""SP6 6.1, 6.2: one file per entry under .plumb/log/<kind>/ (SR-073)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from plumb import log
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-073")


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlumbPaths:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


def _files(paths: PlumbPaths) -> list[Path]:
    return sorted(paths.log_dir.glob("*/*.json"))


def test_one_file_per_entry_under_kind(paths: PlumbPaths) -> None:
    first = log.append(paths, "events", "approval", {"records": [{"id": "SR-001"}]})
    second = log.append(paths, "events", "prompt", {"digest": "x"})
    files = _files(paths)
    assert [f.parent.name for f in files] == ["approval", "prompt"]
    assert first.name == f"approval/{files[0].name}" and first.offset == -1
    raw = json.loads(files[0].read_bytes())
    assert set(raw) == {"v", "kind", "at", "marker", "payload", "prev", "digest"}
    assert raw["digest"] == first.digest == log.entry_digest(raw)
    assert files[0].read_bytes().endswith(b"}\n")
    assert second.prev == first.digest
    assert not paths.log_events.exists()  # nothing goes to the legacy file
    assert not list(paths.log_dir.glob("*/.*"))  # no temporary file left behind


def test_stream_of_kind_evidence_and_events(paths: PlumbPaths) -> None:
    assert log.stream_of("test-run") == "evidence"
    assert log.stream_of("merge-evidence") == "evidence"
    for kind in ("approval", "revocation", "prompt", "repin", "judgment", "renumber",
                 "conflict-resolution", "some-later-kind"):
        assert log.stream_of(kind) == "events"
    run = log.append(paths, "evidence", "test-run", {"run_id": "r1"})
    event = log.append(paths, "events", "repin", {})
    assert run.prev is None and event.prev is None  # one chain per stream
    assert [e.kind for e in log.read(paths, "evidence")] == ["test-run"]
    assert [e.kind for e in log.read(paths, "events")] == ["repin"]
    with pytest.raises(ValueError):
        log.append(paths, "events", "test-run", {})
    with pytest.raises(ValueError):
        log.append(paths, "events", "../escape", {})


_WRITER = """
import sys, time
from pathlib import Path
from plumb import log
from plumb.paths import PlumbPaths
paths = PlumbPaths(Path(sys.argv[1]))
start = float(sys.argv[2])
while time.time() < start:
    pass
for i in range(10):
    log.append(paths, "events", "prompt", {"writer": sys.argv[3], "i": i})
"""


def test_same_second_writers_never_replace(paths: PlumbPaths) -> None:
    """SR-073 EX-2: two writers in one worktree in the same second both keep their entry."""
    import time

    start = str(time.time() + 1.0)
    procs = [subprocess.Popen([sys.executable, "-c", _WRITER, str(paths.root), start, w])
             for w in ("a", "b")]
    assert all(p.wait(timeout=60) == 0 for p in procs)
    files = _files(paths)
    assert len(files) == 20 and len({f.name for f in files}) == 20
    payloads = {(e.payload["writer"], e.payload["i"]) for e in log.read(paths, "events")}
    assert len(payloads) == 20
    assert log.verify_chain(paths, "events") == []


def test_prev_is_stream_head(paths: PlumbPaths) -> None:
    entries = [log.append(paths, "events", "repin", {"i": i}) for i in range(3)]
    head = json.loads(paths.log_head.read_text(encoding="utf-8"))
    assert head["events"] == {"digest": entries[-1].digest, "name": entries[-1].name}
    assert [e.prev for e in entries] == [None, entries[0].digest, entries[1].digest]


def test_head_rebuilt_by_scan_when_deleted(paths: PlumbPaths) -> None:
    """SR-073 EX-4: with the head pointer deleted, the next prev is the latest entry."""
    log.append(paths, "events", "repin", {"i": 0})
    last = log.append(paths, "events", "repin", {"i": 1})
    paths.log_head.unlink()
    after = log.append(paths, "events", "repin", {"i": 2})
    assert after.prev == last.digest
    # a head naming a vanished file is rebuilt too
    data = json.loads(paths.log_head.read_text(encoding="utf-8"))
    data["events"]["name"] = "repin/20000101T000000.000001Z-deadbeef.json"
    paths.log_head.write_text(json.dumps(data), encoding="utf-8")
    assert log.append(paths, "events", "repin", {"i": 3}).prev == after.digest


def test_head_starts_from_legacy_lines(paths: PlumbPaths) -> None:
    """Before the migration, the first entry file chains to the last legacy line."""
    from logutil import legacy_entry, write_legacy

    first = legacy_entry("repin", {"i": 0}, None)
    second = legacy_entry("repin", {"i": 1}, first["digest"], at="2026-10-05T12:00:01Z")
    write_legacy(paths.root, "events", [first, second])
    assert log.append(paths, "events", "repin", {"i": 2}).prev == second["digest"]


def test_name_stamp_and_suffix_parse(paths: PlumbPaths) -> None:
    entry = log.append(paths, "events", "repin", {})
    file_name = entry.name.split("/", 1)[1]
    stamp, micros, suffix = log.parse_name(file_name)
    assert len(stamp) == 15 and stamp[8] == "T"
    assert micros != "000000" and len(suffix) == 8  # .000000 is reserved for migrations
    assert not log.is_migrated_name(file_name)
    raw = {"at": "2026-10-05T16:53:44Z", "digest": "sha256:" + "0123456789abcdef" * 4}
    name = log.migrated_name(raw)
    assert name == "20261005T165344.000000Z-89abcdef.json"
    assert log.is_migrated_name(name) and log.parse_name(name)[2] == "89abcdef"
    assert log.parse_name("events.jsonl") is None
    assert log.parse_name("20261005T165344.000000Z-89abcdeg.json") is None
    assert log.migrated_name({"at": "yesterday", "digest": raw["digest"]}) is None
