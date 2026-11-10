"""CAPTURE CS3: iaso jev calibrate measures JEV on the owner's own decisions (R12.1,
R13 Q1; sp2 8.3, SR-042)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import JevStub, event_kinds, run, use_jev
from jev_fixtures import default_noul, owner_decisions

from iaso.api import open_core
from iaso.capture.calibrate import calibrate, labelled_set

pytestmark = pytest.mark.sr("SR-252")


@pytest.fixture
def stub():
    instance = JevStub(default_noul)
    yield instance
    instance.close()


def test_mixed_evidence_passes_and_records_the_split(repo: Path, write_record, monkeypatch,
                                                     stub, capsys) -> None:
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record)
    assert run(repo, "jev", "calibrate") == 0
    out = capsys.readouterr().out
    assert "intent-readback: passing" in out
    assert "3 real, 3 of 40 generated" in out
    [entry] = list(open_core(repo).log_read("events", ["calibration"]))
    result = entry.payload["per_kind"]["intent-readback"]
    assert (result["items"], result["positives"], result["real_negatives"]) == (23, 20, 3)
    assert (result["generated_negatives"], result["generated_counted"]) == (40, 3)
    assert result["false_accept"] == 0.0 and result["recall"] == 1.0
    assert entry.payload["model_version"] == "jev-1.13.0"
    assert not entry.payload["per_kind"]["example-restatement"]["passing"]
    # iaso jev status shows the real/generated split (R13 Q1)
    assert run(repo, "jev", "status") == 0
    status = capsys.readouterr().out
    assert "calibrated against: jev-1.13.0" in status
    assert "'no' examples 3 real + 3 generated counted (of 40)" in status


def test_fewer_than_twenty_decisions_is_not_passing(repo: Path, write_record, monkeypatch,
                                                    stub, capsys) -> None:
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record, intents=15)
    assert run(repo, "jev", "calibrate") == 1
    [entry] = list(open_core(repo).log_read("events", ["calibration"]))
    result = entry.payload["per_kind"]["intent-readback"]
    assert not result["passing"] and "18 of your decisions, 20 needed" in result["reasons"]
    capsys.readouterr()
    assert run(repo, "config", "auto-approve", "on") == 0  # EX-1 (DEC-143): on needs none
    from iaso.capture.autoapprove import auto_approve_state

    assert auto_approve_state(open_core(repo)).effective and "config" in event_kinds(repo)


def test_generated_no_examples_count_up_to_half(repo: Path, write_record, monkeypatch,
                                                stub) -> None:
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record, intents=22, revoked=2)
    _, results = calibrate(open_core(repo))
    result = results["intent-readback"]
    assert (result.real_negatives, result.generated_counted, result.negatives) == (2, 2, 4)
    assert not result.passing


def test_threshold_is_above_the_highest_no(repo: Path, write_record, monkeypatch) -> None:
    def noul(state: str) -> float:
        claim = state.split("Claim (", 1)[-1]
        return 0.93 if "UNFAITHFUL" in claim else default_noul(state)

    stub = JevStub(noul)
    try:
        use_jev(repo, stub, monkeypatch)
        owner_decisions(repo, write_record)
        _, results = calibrate(open_core(repo))
    finally:
        stub.close()
    result = results["intent-readback"]
    assert result.threshold is not None and result.threshold > 0.93
    assert result.passing and result.false_accept == 0.0


def test_a_generated_no_accepted_fails(repo: Path, write_record, monkeypatch) -> None:
    def noul(state: str) -> float:
        claim = state.split("Claim (", 1)[-1]
        return 0.97 if "won't:" in claim else default_noul(state)

    stub = JevStub(noul)
    try:
        use_jev(repo, stub, monkeypatch)
        owner_decisions(repo, write_record)
        _, results = calibrate(open_core(repo))
    finally:
        stub.close()
    assert not results["intent-readback"].passing  # no positive clears the threshold


def test_no_judge_reports_judging_unavailable(repo: Path, write_record, capsys) -> None:
    """INT-029: with no judge configured, calibration says so; nothing stands in."""
    owner_decisions(repo, write_record, intents=2, revoked=0)
    assert run(repo, "jev", "calibrate") == 1
    out = capsys.readouterr().out
    assert "judging unavailable" in out and "judgment.backend" in out
    assert "calibration" not in event_kinds(repo)


def test_labelled_set_variations(repo: Path, write_record) -> None:
    owner_decisions(repo, write_record, intents=1, revoked=1)
    items = labelled_set(open_core(repo))
    sources = sorted(i.source for i in items)
    assert sources == ["generated:flipped-result", "generated:will-to-wont", "owner",
                       "revoked"]
