"""SR-190: a judgment on a record whose premise is its quote alone says so, a calibration
counts those items and plumb jev status prints the count; nothing is decided by it."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import JevStub, use_jev
from jev_fixtures import owner_decisions

from plumb.api import open_core
from plumb.capture.calibrate import calibrate
from plumb.capture.jevcmd import jev_status, status_lines

pytestmark = pytest.mark.sr("SR-241")


def test_ex2_calibration_counts_quote_only_items_and_status_prints_it(
        repo: Path, write_record, monkeypatch) -> None:
    stub = JevStub()
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record)                    # none of its intents names a prompt
    entry, results = calibrate(open_core(repo))
    kind = results["intent-readback"]
    assert kind.items > 0 and kind.quote_only == kind.items
    assert entry.payload["per_kind"]["intent-readback"]["quote_only"] == kind.items
    line = f"quote-only: {kind.quote_only} of {kind.items}"
    assert any(line in text for text in status_lines(jev_status(open_core(repo))))
    stub.close()
