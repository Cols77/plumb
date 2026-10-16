"""SP6 6.3: readers accept both formats, deduplicated and ordered (SR-073, SR-074)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from logutil import legacy_entry, write_legacy

from plumb import log
from plumb.normalize import canonical_json
from plumb.paths import PlumbPaths


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlumbPaths:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


def _put(paths: PlumbPaths, raw: dict, name: str | None = None) -> str:
    """Place an entry file as a merge would bring it."""
    file_name = name or log.migrated_name(raw)
    directory = paths.log_kind_dir(raw["kind"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / file_name).write_bytes(canonical_json(raw) + b"\n")
    return f"{raw['kind']}/{file_name}"


@pytest.mark.sr("SR-232")
def test_order_at_then_chain_then_name(paths: PlumbPaths) -> None:
    a = legacy_entry("approval", {"n": "a"}, None, at="2026-10-05T12:00:05Z")
    # same second, chained after a, but its name sorts first
    b = legacy_entry("revocation", {"n": "b"}, a["digest"], at="2026-10-05T12:00:05Z")
    early = legacy_entry("prompt", {"n": "early"}, None, at="2026-10-05T11:00:00Z")
    # a skewed clock: chained after b but stamped earlier; the chain wins
    skew = legacy_entry("prompt", {"n": "skew"}, b["digest"], at="2026-10-05T12:00:04Z")
    _put(paths, a, "20261005T120005.000001Z-ffffffff.json")
    _put(paths, b, "20261005T120005.000001Z-00000000.json")
    _put(paths, early)
    _put(paths, skew)
    order = [e.payload["n"] for e in log.read(paths, "events")]
    assert order == ["early", "a", "b", "skew"]
    # unrelated entries of one second: by name
    c = legacy_entry("prompt", {"n": "c"}, None, at="2026-10-05T13:00:00Z")
    d = legacy_entry("prompt", {"n": "d"}, None, at="2026-10-05T13:00:00Z")
    _put(paths, c, "20261005T130000.000002Z-00000001.json")
    _put(paths, d, "20261005T130000.000001Z-00000002.json")
    assert [e.payload["n"] for e in log.read(paths, "events")][-2:] == ["d", "c"]


@pytest.mark.sr("SR-232")
def test_both_formats_deduplicated_by_digest(paths: PlumbPaths) -> None:
    first = legacy_entry("repin", {"i": 0}, None)
    second = legacy_entry("repin", {"i": 1}, first["digest"], at="2026-10-05T12:00:01Z")
    write_legacy(paths.root, "events", [first, second])
    migrated = _put(paths, first)  # the first line also exists as its migrated file
    new = log.append(paths, "events", "approval", {"records": []})
    read = list(log.read(paths, "events"))
    assert [e.digest for e in read] == [first["digest"], second["digest"], new.digest]
    assert read[0].name == migrated and read[0].offset == -1
    assert read[1].name == "events.jsonl:2" and read[1].offset > 0
    assert [e.kind for e in log.read(paths, "events", kinds=["approval"])] == ["approval"]
    assert log.verify_chain(paths, "events") == []


@pytest.mark.sr("SR-232")
def test_pack_cache_reads_only_new_files(paths: PlumbPaths,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    for i in range(3):
        log.append(paths, "events", "repin", {"i": i})
    list(log.read(paths, "events"))
    assert paths.log_pack("events").is_file()
    opened: list[str] = []
    real = Path.read_bytes

    def spy(self: Path) -> bytes:
        opened.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    assert len(list(log.read(paths, "events"))) == 3
    assert opened == []  # warm: one listing, no entry file read
    new = log.append(paths, "events", "repin", {"i": 3})
    opened.clear()
    assert len(list(log.read(paths, "events"))) == 4
    assert opened == [new.name.split("/", 1)[1]]


@pytest.mark.sr("SR-232")
def test_pack_cache_drops_vanished_names(paths: PlumbPaths) -> None:
    entries = [log.append(paths, "events", "repin", {"i": i}) for i in range(3)]
    list(log.read(paths, "events"))
    (paths.log_dir / entries[1].name).unlink()
    names = [e.name for e in log.read(paths, "events")]
    assert names == [entries[0].name, entries[2].name]
    pack = json.loads(paths.log_pack("events").read_text(encoding="utf-8"))
    assert entries[1].name not in pack["files"]


@pytest.mark.sr("SR-232")
def test_corrupt_pack_cache_rebuilt(paths: PlumbPaths) -> None:
    entries = [log.append(paths, "events", "repin", {"i": i}) for i in range(2)]
    list(log.read(paths, "events"))
    paths.log_pack("events").write_text("{not json", encoding="utf-8")
    assert [e.digest for e in log.read(paths, "events")] == [e.digest for e in entries]
    pack = json.loads(paths.log_pack("events").read_text(encoding="utf-8"))
    assert set(pack["files"]) == {e.name for e in entries}
    # a cached entry whose file changed on disk is read again, not trusted
    path = paths.log_dir / entries[0].name
    path.write_text(path.read_text(encoding="utf-8").replace('"i":0', '"i":7'),
                    encoding="utf-8")
    assert next(iter(log.read(paths, "events"))).payload == {"i": 7}


@pytest.mark.sr("SR-232")
def test_since_skips_applied_names(paths: PlumbPaths) -> None:
    entries = [log.append(paths, "events", "repin", {"i": i}) for i in range(3)]
    applied = {entries[0].name, entries[1].name}
    assert [e.name for e in log.read(paths, "events", since=applied)] == [entries[2].name]
