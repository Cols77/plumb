"""R3: the reader's threshold is learned from the owner's labelled answers (SR-101 EX-14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.fakes import as_worker
from understand.test_read_job import SESSION, make_core, record_text

from iaso.api import open_core
from iaso.understand.threshold import MIN_LABELS, reader_threshold

pytestmark = pytest.mark.sr("SR-214")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(1)])


def agreed(core, confidence: float) -> None:
    """The owner agreed: an owner-words confirmation at that confidence."""
    with as_worker(core.root, SESSION):
        core.log_append("events", "approval", {
            "by": "owner-words", "session": SESSION, "job": "read-0", "records": [],
            "prompt_digest": "sha256:0", "evidence": "ok", "confidence": confidence})


def disagreed(core, confidence: float) -> None:
    """The owner said the reader misread: a misread rejection at that confidence."""
    core.log_append("events", "rejection", {
        "by": "owner-words", "session": SESSION, "job": "read-0", "records": [],
        "reason": "capture-error", "confidence": confidence, "prompt_digest": "sha256:0"})


def trial(core, answer: str, confidence: float) -> None:
    core.log_append("events", "trial", {"card": "t1", "items": [], "answers": [
        {"answer": answer, "confidence": confidence}]})


def test_ex14_twenty_answers_support_0_8(core) -> None:
    for confidence in (0.5, 0.6, 0.7, 0.75):
        disagreed(core, confidence)
    for confidence in (0.8, 0.82, 0.85, 0.85, 0.88, 0.9, 0.9, 0.92, 0.95, 0.95, 0.95, 0.97,
                       0.97, 0.99, 0.99, 1.0):
        agreed(core, confidence)
    assert reader_threshold(open_core(core.root)) == 0.8


def test_starting_value_until_enough_labels(core) -> None:
    for _ in range(MIN_LABELS - 1):
        agreed(core, 0.6)
    assert reader_threshold(open_core(core.root)) == 0.9
    agreed(core, 0.6)
    assert reader_threshold(open_core(core.root)) == 0.6
    assert MIN_LABELS == 20


def test_a_disagreement_raises_the_threshold(core) -> None:
    for confidence in [0.85] * 10 + [0.95] * 10:
        agreed(core, confidence)
    assert reader_threshold(open_core(core.root)) == 0.85
    disagreed(core, 0.9)
    assert reader_threshold(open_core(core.root)) == 0.95


def test_trial_yes_and_no_are_labels_too(core) -> None:
    for _ in range(10):
        trial(core, "yes", 0.9)
    for _ in range(9):
        trial(core, "yes", 0.8)
    trial(core, "no", 0.7)
    assert reader_threshold(open_core(core.root)) == 0.8


def test_configured_start_is_used_without_labels(core, repo: Path) -> None:
    (repo / ".iaso" / "config.yaml").write_text(
        "understand:\n  reader_threshold_start: 0.95\n", encoding="utf-8")
    assert reader_threshold(open_core(repo)) == 0.95
