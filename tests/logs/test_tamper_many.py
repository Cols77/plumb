"""SR-322 EX-1, EX-2: validate ignores an unheld ``prev`` but still reports an edited entry."""

from __future__ import annotations

from pathlib import Path

import pytest
from logutil import legacy_entry, tamper, write_legacy

from iaso import log
from iaso.normalize import canonical_json
from iaso.paths import IasoPaths


@pytest.fixture
def paths(tmp_path: Path) -> IasoPaths:
    p = IasoPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


@pytest.mark.sr("SR-322")
def test_ex1_prev_naming_another_sessions_entry_is_no_error(paths: IasoPaths) -> None:
    other = legacy_entry("repin", {"other": True}, None)  # not in this checkout
    mine = legacy_entry("repin", {"mine": True}, other["digest"], at="2026-10-05T12:00:01Z")
    directory = paths.log_kind_dir("repin")
    directory.mkdir(parents=True)
    (directory / "20261005T120001.000001Z-0000000a.json").write_bytes(canonical_json(mine) + b"\n")
    assert log.verify_chain(paths, "events") == []


@pytest.mark.sr("SR-322")
def test_ex2_edited_committed_entry_is_reported(paths: IasoPaths) -> None:
    log.append(paths, "events", "repin", {"i": 1})
    name = tamper(paths.root, "events", 0, lambda t: t.replace('"i":1', '"i":2'))
    assert log.verify_chain(paths, "events") == [
        f"{name}: digest does not match the entry (modified entry)"]


@pytest.mark.sr("SR-322")
def test_legacy_line_with_an_unheld_prev_is_no_error_but_an_edit_is(paths: IasoPaths) -> None:
    other = legacy_entry("repin", {"other": True}, None)  # not in this checkout
    mine = legacy_entry("repin", {"i": 1}, other["digest"], at="2026-10-05T12:00:01Z")
    write_legacy(paths.root, "events", [mine])
    assert log.verify_chain(paths, "events") == []
    tamper(paths.root, "events", 0, lambda t: t.replace('"i":1', '"i":2'))
    assert any("events.jsonl line 1" in p and "digest" in p
               for p in log.verify_chain(paths, "events"))
