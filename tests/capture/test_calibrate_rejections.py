"""SR-096 (DEC-026 A): a rejected read-back counts as a calibration 'no' only when it
misread the owner's words. A capture-error rejection at hash H is a real 'no' of that
record's kind (counted with revoked records, not as generated); an intent-change rejection
gets no label; a later version (hash H2) stays unlabelled until the owner answers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import JevStub, record_text, use_jev
from jev_fixtures import default_noul, owner_decisions

from iaso import approvals
from iaso.api import open_core
from iaso.capture.calibrate import calibrate, labelled_set

pytestmark = pytest.mark.sr("SR-215")


@pytest.fixture
def stub():
    instance = JevStub(default_noul)
    yield instance
    instance.close()


def _log(root: Path, text: str) -> str:
    digest = approvals.prompt_digest(text)
    prompts = root / ".iaso" / "session" / "prompts.jsonl"
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"digest": digest, "session": "s1",
                                 "at": "2026-10-06T03:00:00Z", "text": text,
                                 "via": "hook"}) + "\n")
    return digest


def _propose(repo: Path, write_record, record_id: str, readback: str) -> None:
    write_record(repo, record_text(record_id, f"wish {record_id}", quote="cap the spend",
                                   readback=readback, will=[readback]))


def _reject(repo: Path, record_id: str, reason: str, words: str | None = None) -> None:
    """The rejection as the worker logs it from the reader's reading of the owner's message
    (the agent-run relay that used to log it no longer exists, SR-101 EX-9)."""
    from iaso.capture.calibrate import snapshot
    from iaso.normalize import sha256_text

    words = words or f"{record_id}: that is not what I asked"
    core = open_core(repo)
    record = core.index()[record_id]
    item = {"id": record_id, "hash": record.hash, **snapshot(core.index(), record, core)}
    core.log_append("events", "rejection", {
        "by": "owner-words", "records": [item],
        "reason": reason if reason in ("capture-error", "intent-change") else "intent-change",
        "prompt_digest": _log(repo, words), "quote": words, "quote_digest": sha256_text(words),
        "confidence": 0.99})


def _rejected(repo: Path) -> list:
    return [i for i in labelled_set(open_core(repo)) if i.source == "rejected"]


def test_ex1_capture_error_is_a_real_no_and_the_new_version_is_unlabelled(
        repo: Path, write_record, monkeypatch, stub) -> None:
    use_jev(repo, stub, monkeypatch)
    _propose(repo, write_record, "INT-016", "UNFAITHFUL records your solution")
    old_hash = open_core(repo).index()["INT-016"].hash
    _reject(repo, "INT-016", "capture-error")
    _propose(repo, write_record, "INT-016", "cap the spend")  # recaptured: hash H2
    assert open_core(repo).index()["INT-016"].hash != old_hash
    [item] = _rejected(repo)
    assert (item.record, item.kind, item.label) == ("INT-016", "intent-readback", "no")
    assert any("UNFAITHFUL" in h for h in item.hypotheses)  # the old text, not the new
    assert not [i for i in labelled_set(open_core(repo))
                if i.record == "INT-016" and i.source != "rejected"
                and not i.source.startswith("generated")]


def test_ex1_counts_as_a_real_negative_not_a_generated_one(
        repo: Path, write_record, monkeypatch, stub) -> None:
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record, intents=20, revoked=2)
    _propose(repo, write_record, "INT-016", "UNFAITHFUL records your solution")
    _reject(repo, "INT-016", "capture-error")
    _, results = calibrate(open_core(repo))
    result = results["intent-readback"]
    assert result.real_negatives == 3 and result.items == 23


def test_ex2_intent_change_gets_no_label(repo: Path, write_record, monkeypatch, stub) -> None:
    use_jev(repo, stub, monkeypatch)
    _propose(repo, write_record, "INT-013", "register agents")
    _reject(repo, "INT-013", "intent-change", "INT-013: no. I don't know yet")
    assert _rejected(repo) == []
    assert not [i for i in labelled_set(open_core(repo)) if i.record == "INT-013"]


def test_ex3_an_unreadable_reason_gives_no_label(repo: Path, write_record, monkeypatch,
                                                 stub) -> None:
    use_jev(repo, stub, monkeypatch)
    _propose(repo, write_record, "INT-013", "register agents")
    _reject(repo, "INT-013", "whatever", "INT-013: no")
    assert _rejected(repo) == []


def test_a_rejection_is_one_item_however_often_it_is_relayed(
        repo: Path, write_record, monkeypatch, stub) -> None:
    use_jev(repo, stub, monkeypatch)
    _propose(repo, write_record, "INT-016", "UNFAITHFUL records your solution")
    _reject(repo, "INT-016", "capture-error", "INT-016: wrong")
    _reject(repo, "INT-016", "capture-error", "INT-016: that is wrong")
    assert len(_rejected(repo)) == 1


def test_a_version_the_owner_later_confirmed_is_not_a_no(
        repo: Path, write_record, monkeypatch, stub) -> None:
    use_jev(repo, stub, monkeypatch)
    _propose(repo, write_record, "INT-016", "cap the spend")
    _reject(repo, "INT-016", "capture-error")
    approvals.approve(open_core(repo), ["INT-016"])
    assert _rejected(repo) == []
