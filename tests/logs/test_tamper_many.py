"""SR-322 EX-1, EX-2: validate ignores an unheld ``prev`` but still reports an edited entry."""

from __future__ import annotations

from pathlib import Path

import pytest
from logutil import legacy_entry, tamper

from plumb import log
from plumb.normalize import canonical_json
from plumb.paths import PlumbPaths


@pytest.fixture
def paths(tmp_path: Path) -> PlumbPaths:
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


@pytest.mark.sr("SR-322")
def test_ex1_prev_naming_another_sessions_entry_is_no_error(paths: PlumbPaths) -> None:
    other = legacy_entry("repin", {"other": True}, None)  # not in this checkout
    mine = legacy_entry("repin", {"mine": True}, other["digest"], at="2026-10-05T12:00:01Z")
    directory = paths.log_kind_dir("repin")
    directory.mkdir(parents=True)
    (directory / "20261005T120001.000001Z-0000000a.json").write_bytes(canonical_json(mine) + b"\n")
    assert log.verify_chain(paths, "events") == []


@pytest.mark.sr("SR-322")
def test_ex2_edited_committed_entry_is_reported(paths: PlumbPaths) -> None:
    log.append(paths, "events", "repin", {"i": 1})
    name = tamper(paths.root, "events", 0, lambda t: t.replace('"i":1', '"i":2'))
    assert log.verify_chain(paths, "events") == [
        f"{name}: digest does not match the entry (modified entry)"]
