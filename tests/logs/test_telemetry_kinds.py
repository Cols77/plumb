"""SR-376: judgment entries are telemetry (moved whole into the segment at a landing, live files
ignored by git), the offer kind is gone, and the chain still validates through the segments."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from loadbound import assert_within
from logutil import legacy_entry

from logs.gitrepo import make_repo, run_git
from plumb import log
from plumb.api import open_core
from plumb.boundary import landing
from plumb.normalize import canonical_json
from plumb.validate import validate

pytestmark = pytest.mark.sr("SR-376")

OLD, LANDING = "2026-10-01T10:00:00Z", "2026-10-20T00:00:00Z"


def _put_judgments(root: Path, n: int, prev: str | None = None, at: str = OLD) -> str | None:
    folder = root / ".plumb" / "log" / "judgment"
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        raw = legacy_entry("judgment", {"subject": "SR-001", "n": i}, prev, at=at)
        (folder / log.migrated_name(raw)).write_bytes(canonical_json(raw) + b"\n")
        prev = raw["digest"]
    return prev


def _compact(root: Path) -> list[str]:
    core = open_core(root)
    return log.archive(core.paths, landing.compaction(core, LANDING, set()))


def test_judgment_compacts_whole_at_landing(tmp_path: Path) -> None:
    """EX-1: every judgment older than the landing moves, though nothing tracks it and its
    record is live; a newer one stays."""
    root = make_repo(tmp_path / "r")
    _put_judgments(root, 30)
    _put_judgments(root, 2, at="2026-10-25T10:00:00Z")
    _compact(root)
    folder = root / ".plumb" / "log" / "judgment"
    assert len(list(folder.glob("*.json"))) == 2
    assert len((folder / log.SEGMENT).read_bytes().splitlines()) == 30


def test_live_judgment_files_are_ignored_by_git(tmp_path: Path) -> None:
    """EX-2: the new file is ignored; the segment is not."""
    root = make_repo(tmp_path / "r")
    _put_judgments(root, 1)
    segment = root / ".plumb" / "log" / "judgment" / log.SEGMENT
    segment.write_bytes(b"{}\n")
    status = run_git(root, "status", "--porcelain", "-uall").stdout
    assert ".plumb/log/judgment/archive.jsonl" in status
    assert ".plumb/log/judgment/2026" not in status


def test_no_offer_kind() -> None:
    """EX-3: log.py does not know the kind and drawing a card writes no log entry."""
    assert "offer" not in log.SHARED_KINDS | log.LOCAL_KINDS


def test_validate_chains_through_segments(tmp_path: Path) -> None:
    """EX-5: a chain broken across live files and the segment checks clean."""
    root = make_repo(tmp_path / "r")
    last = _put_judgments(root, 5)
    _put_judgments(root, 2, prev=last, at="2026-10-25T10:00:00Z")
    _compact(root)
    assert log.verify_chain(open_core(root).paths, "events") == []
    assert [f for f in validate(open_core(root)) if f.severity == "error"] == []


@pytest.mark.load_bound
def test_brief_under_three_seconds(tmp_path: Path) -> None:
    """EX-4: 20,000 archived judgments do not slow the brief."""
    root = make_repo(tmp_path / "r")
    segment = root / ".plumb" / "log" / "judgment" / log.SEGMENT
    segment.parent.mkdir(parents=True, exist_ok=True)
    prev, lines = None, []
    for i in range(20_000):
        raw = legacy_entry("judgment", {"subject": "SR-001", "n": i}, prev)
        lines.append(canonical_json(raw))
        prev = raw["digest"]
    segment.write_bytes(b"\n".join(lines) + b"\n")
    start = time.perf_counter()
    open_core(root).brief_lines()
    assert_within(time.perf_counter() - start, 3.0, "plumb brief with 20,000 archived judgments")
