"""SP6 6.3, 13: a warm read of 2000 events stays cheap through the pack cache (SR-073)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from logutil import legacy_entry

from plumb import log
from plumb.normalize import canonical_json
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-073")

KINDS = ("approval", "prompt", "repin", "judgment", "revocation")


def _populate(paths: PlumbPaths, n: int) -> None:
    prev = None
    for i in range(n):
        kind = KINDS[i % len(KINDS)]
        raw = legacy_entry(kind, {"i": i, "records": [{"id": f"SR-{i % 80:03d}",
                                                         "hash": "sha256:" + "a" * 64}],
                                  "quote": "ok, confirm it"}, prev,
                           at=f"2026-10-{1 + i // 86400:02d}T{(i // 3600) % 24:02d}:"
                              f"{(i // 60) % 60:02d}:{i % 60:02d}Z")
        directory = paths.log_kind_dir(kind)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / log.migrated_name(raw)).write_bytes(canonical_json(raw) + b"\n")
        prev = raw["digest"]


def _timed(paths: PlumbPaths) -> tuple[float, int]:
    start = time.perf_counter()
    count = sum(1 for _ in log.read(paths, "events"))
    return time.perf_counter() - start, count


def test_read_cost(tmp_path: Path) -> None:
    """Cold: no pack cache, every entry file parsed. The very first open of a freshly
    written file also pays the operating system's on-access scan (about 7 ms per file on a
    Windows machine with Defender), once per file and outside plumb, so the cold read is
    timed after one priming pass. Warm: one listing per kind plus the cache."""
    paths = PlumbPaths(tmp_path)
    _populate(paths, 2000)
    assert _timed(paths)[1] == 2000  # priming pass
    paths.log_pack("events").unlink()
    cold, count = _timed(paths)
    assert count == 2000
    assert cold < 1.0, f"cold read took {cold:.3f}s"
    warm = min(_timed(paths)[0] for _ in range(5))  # best of 5: other processes share the CPU
    assert warm < 0.060, f"warm read took {warm * 1000:.1f} ms"
