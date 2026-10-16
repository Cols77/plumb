"""SP6 6.3, 13: reading 2000 events stays cheap, cold in a new worktree and warm (SR-073).

The cold read is timed in a worktree that ``git worktree add`` has just written, with no
priming pass: there the first open of every entry file pays the operating system's on-access
scan (about 7 ms per file on Windows with Defender), so the reader must take the entries from
git's object store (``log._read_uncached``)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from logutil import legacy_entry

from logs.gitrepo import add_worktree, commit_all, make_repo, run_git
from plumb import log
from plumb.normalize import canonical_json
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-232")

KINDS = ("approval", "prompt", "repin", "judgment", "revocation")


def populate(paths: PlumbPaths, n: int, start: int = 0) -> None:
    """``n`` chained event entries written as migrated entry files."""
    prev = None
    for i in range(start, start + n):
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
    """Cold: a worktree ``git worktree add`` has just written, beside the main worktree
    whose hooks have read the log; no pack cache there and no priming pass. Cold again: a
    fresh clone (git's objects packed, as from a remote). Warm: one listing per kind plus
    the cache."""
    main = make_repo(tmp_path / "main")
    populate(PlumbPaths(main), 2000)
    commit_all(main, "2000 events")
    assert _timed(PlumbPaths(main))[1] == 2000  # the main worktree's own sessions
    paths = PlumbPaths(add_worktree(main, tmp_path / "wt", "wt"))
    assert not paths.log_pack("events").exists()
    cold, count = _timed(paths)
    assert count == 2000
    assert cold < 1.0, f"cold read in a fresh worktree took {cold:.3f}s"
    clone = tmp_path / "clone"
    run_git(tmp_path, "clone", "-q", main.as_uri(), str(clone))
    cold, count = _timed(PlumbPaths(clone))
    assert count == 2000
    assert cold < 1.0, f"cold read in a fresh clone took {cold:.3f}s"
    warm = min(_timed(paths)[0] for _ in range(10))  # best of 10: other processes share the CPU
    assert warm < 0.060, f"warm read took {warm * 1000:.1f} ms"
