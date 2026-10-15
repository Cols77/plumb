"""SR-190: a judgment on a record whose premise is its quote alone says so, a calibration
counts those items and plumb jev status prints the count; nothing is decided by it."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import JevStub, log_prompt, record_text, use_jev
from jev_fixtures import owner_decisions

from plumb.api import open_core
from plumb.capture.calibrate import calibrate
from plumb.capture.jevcmd import jev_status, status_lines
from plumb.capture.triage import triage

pytestmark = pytest.mark.sr("SR-190")

QUOTE = "please build feature alpha"


def judged(repo: Path, write_record, monkeypatch, **fields) -> dict:
    stub = JevStub()
    use_jev(repo, stub, monkeypatch)
    write_record(repo, record_text("INT-100", "wish", quote=QUOTE, readback="build alpha",
                                   will=["alpha"], **fields))
    triage(open_core(repo), ["INT-100"])
    stub.close()
    return [e for e in open_core(repo).events() if e.kind == "judgment"][-1].payload


def test_ex1_no_prompt_named_marks_the_judgment_quote_only(
        repo: Path, write_record, monkeypatch) -> None:
    payload = judged(repo, write_record, monkeypatch)
    assert payload["premise"] == "quote-only"
    assert payload["premise_reason"].startswith("quote not verified")


def test_ex3_a_whole_message_premise_carries_no_mark(
        repo: Path, write_record, monkeypatch) -> None:
    digest = log_prompt(repo, f"{QUOTE} and make it fast")
    payload = judged(repo, write_record, monkeypatch, prompt=digest.removeprefix("sha256:")[:16])
    assert "premise" not in payload and "premise_reason" not in payload


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
