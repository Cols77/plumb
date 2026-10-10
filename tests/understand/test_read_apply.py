"""R2/R3: applying the reader's answers after exact checks only (SR-101)."""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path

import pytest
from understand.fakes import FakeDispatcher, as_worker, owner_level
from understand.test_read_job import (
    SESSION,
    ctx_for,
    int_text,
    log_prompt,
    make_core,
    open_card,
    record_text,
    state,
)

from plumb.api import open_core
from plumb.log import append, stream_of
from plumb.present import owner_text
from plumb.understand import cardstore, files, read

pytestmark = pytest.mark.sr("SR-101")


def write_applied(core, applied) -> None:
    """What the worker does with an ``Applied``: cards, then log entries (as the worker)."""
    with as_worker(core.root, SESSION):
        if applied.cards or applied.closed:
            replaced = {c.id for c in applied.cards}
            kept = [dataclasses.replace(c, status="closed") if c.id in applied.closed else c
                    for c in cardstore.own_cards(core.root, SESSION) if c.id not in replaced]
            cardstore.save(core.root, SESSION, [*kept, *applied.cards])
        for entry in applied.entries:
            kind = str(entry["kind"])
            append(core.paths, stream_of(kind), kind, dict(entry["payload"]))


def entry_of(core, record_id: str, answer: str, evidence: str, confidence: float = 0.95,
             **extra) -> dict:
    index = core.index()
    return {"id": record_id, "hash": index[record_id].hash if record_id in index else "",
            "answer": answer, "evidence": evidence, "confidence": confidence, **extra}


def run(core, message: str, shown: list[str], entries: list[dict], *, edit=None):
    """Log the message, build the job, apply the scripted entries, write the result."""
    state(core, shown)
    digest = log_prompt(core, message)
    job = read.build(core, SESSION, message={"digest": digest, "text": message})
    assert job is not None
    if edit:
        edit()
        core = open_core(core.root)
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": entries})
    write_applied(core, applied)
    return open_core(core.root), applied, job


def entries_of(core, kind: str) -> list:
    return [e for e in core.events() if e.kind == kind]


def approvals(core) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in entries_of(core, "approval"):
        if e.payload.get("by") == "owner-words":
            for record in e.payload["records"]:
                out[record["id"]] = dict(e.payload)
    return out


@pytest.fixture
def core(repo: Path, write_record):
    texts = [int_text(8, "Internal features"), record_text(88, "Plain words UX"),
             int_text(24, "Reminder timing"), record_text(97), record_text(98),
             record_text(40), record_text(41), record_text(2), record_text(3)]
    return make_core(repo, write_record, texts)


def test_ex1_int008_ok_confirmed_sr088_change(core) -> None:
    message = ("INT-008 ok, I am not sure I agree with SR-088. In terms of UX, some features "
               "might have to remain internal to plumb.")
    after, applied, job = run(core, message, ["INT-008", "SR-088"], [
        entry_of(core, "INT-008", "accepted", "INT-008 ok"),
        entry_of(core, "SR-088", "change", "some features might have to remain internal to plumb",
                 change="some features stay internal to plumb")])
    assert set(approvals(after)) == {"INT-008"}
    payload = approvals(after)["INT-008"]
    assert payload["evidence"] == "INT-008 ok" and payload["prompt_digest"] == job.inputs[
        "message"]["digest"]
    assert payload["job"] == job.id and payload["confidence"] == 0.95
    assert payload["records"] == [{"id": "INT-008", "hash": core.index()["INT-008"].hash}]
    (card,) = [c for c in cardstore.load(after.root, SESSION)]
    assert "some features stay internal to plumb" in card.issue
    assert card.topic == "Plain words UX" and card.questions[0].record == "SR-088"


def test_ex2_int24_read_as_int024_all_three_confirmed(core) -> None:
    message = "Confirm SR-097, SR-098, INT-24"
    after, _, _ = run(core, message, ["SR-097", "SR-098", "INT-024"], [
        entry_of(core, "SR-097", "accepted", "Confirm SR-097"),
        entry_of(core, "SR-098", "accepted", "SR-098"),
        entry_of(core, "INT-24", "accepted", "INT-24")])
    assert set(approvals(after)) == {"SR-097", "SR-098", "INT-024"}


def test_ex3_unshown_record_shown_as_card_first_then_confirmed_next_answer(core) -> None:
    after, applied, _ = run(core, "ok, and confirm SR-041 too", ["SR-040"], [
        entry_of(core, "SR-040", "accepted", "ok"),
        entry_of(core, "SR-041", "accepted", "confirm SR-041 too", hash="")])
    assert set(approvals(after)) == {"SR-040"}
    (card,) = cardstore.load(after.root, SESSION)
    assert card.kind == "show_first" and card.questions[0].record == "SR-041"
    # the next answer: one read job over the card, the handler confirms the record
    message = "yes"
    digest = log_prompt(after, message, at="2026-10-10T11:00:00Z")
    job = read.build(after, SESSION, message={"digest": digest, "text": message})
    (item,) = job.inputs["cards"]
    assert item["record"] == "SR-041" and item["kind"] == "show_first"
    with as_worker(after.root, SESSION):
        applied = read.apply(after, job, {"entries": [
            {"id": item["id"], "hash": "", "answer": "accepted", "evidence": "yes",
             "confidence": 0.95}]})
    write_applied(after, applied)
    final = open_core(after.root)
    assert set(approvals(final)) == {"SR-040", "SR-041"}
    assert cardstore.load(final.root, SESSION) == []


def test_ex4_confidence_below_threshold_confirms_nothing(core) -> None:
    after, _, _ = run(core, "ok", ["SR-040"], [
        entry_of(core, "SR-040", "accepted", "ok", confidence=0.7)])
    assert approvals(after) == {}
    assert [e.payload["confidence"] for e in entries_of(after, "read-entry")] == [0.7]


def test_ex5_edited_record_confirms_nothing_new_version_shown(core, repo, write_record) -> None:
    def edit():
        write_record(repo, record_text(40, "Plain words UX reworded"))

    after, _, _ = run(core, "ok", ["SR-040", "SR-041"], [
        entry_of(core, "SR-040", "accepted", "ok"),
        entry_of(core, "SR-041", "accepted", "ok")], edit=edit)
    assert set(approvals(after)) == {"SR-041"}
    (card,) = cardstore.load(after.root, SESSION)
    assert card.kind == "show_first" and card.topic == "Plain words UX reworded"


def test_evidence_not_in_message_confirms_nothing(core) -> None:
    after, applied, _ = run(core, "ok", ["SR-040"], [
        entry_of(core, "SR-040", "accepted", "yes, absolutely")])
    assert approvals(after) == {}
    assert applied.notes


def test_message_not_in_log_confirms_nothing(core) -> None:
    state(core, ["SR-040"])
    digest = log_prompt(core, "ok")
    job = read.build(core, SESSION, message={"digest": digest, "text": "ok"})
    core.paths.prompts.write_text("", encoding="utf-8")   # the log no longer holds it
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [entry_of(core, "SR-040", "accepted", "ok")]})
    assert applied.entries == () and applied.cards == ()
    assert applied.notes


def test_rejected_misread_labelled_no(core) -> None:
    after, _, job = run(core, "no, SR-002 got my words wrong", ["SR-002"], [
        entry_of(core, "SR-002", "rejected", "SR-002 got my words wrong",
                 rejection="misread")])
    (rejection,) = entries_of(after, "rejection")
    assert rejection.payload["reason"] == "capture-error"
    assert rejection.payload["records"][0]["id"] == "SR-002"
    assert rejection.payload["by"] == "owner-words" and rejection.payload["job"] == job.id
    assert approvals(after) == {}


def test_rejected_intent_changed_no_label(core) -> None:
    after, _, _ = run(core, "no, I want something else for SR-002", ["SR-002"], [
        entry_of(core, "SR-002", "rejected", "I want something else for SR-002",
                 rejection="intent-changed")])
    (rejection,) = entries_of(after, "rejection")
    assert rejection.payload["reason"] == "intent-change"


def test_every_entry_is_logged_for_calibration(core) -> None:
    after, _, job = run(core, "ok but not SR-002", ["SR-040", "SR-002"], [
        entry_of(core, "SR-040", "accepted", "ok"),
        entry_of(core, "SR-002", "open", "not SR-002", confidence=0.4)])
    got = {e.payload["id"]: e.payload for e in entries_of(after, "read-entry")}
    assert set(got) == {"SR-040", "SR-002"}
    assert got["SR-002"]["answer"] == "open" and got["SR-002"]["job"] == job.id
    assert got["SR-040"]["message_digest"] == job.inputs["message"]["digest"]


def test_confirmation_lines_say_you_said(core) -> None:
    after, _, job = run(core, "INT-008 ok", ["INT-008"], [
        entry_of(core, "INT-008", "accepted", "INT-008 ok")])
    lines = read.confirmation_lines(after, job.inputs["message"]["digest"])
    assert len(lines) == 1
    assert owner_text.CONFIRM_YOU_SAID.format(evidence="INT-008 ok") in lines[0]
    assert "Internal features" in lines[0]


def test_ex13_nothing_confirmed_while_the_job_runs_confirmed_when_it_returns(
        core, engine_standins) -> None:
    from plumb.understand import queue, worker

    state(core, ["SR-040"])
    digest = log_prompt(core, "ok")
    job = read.build(core, SESSION, message={"digest": digest, "text": "ok"})
    release = threading.Event()
    dispatcher = engine_standins.dispatcher
    dispatcher.block = release
    dispatcher.script = {"read": {"entries": [entry_of(core, "SR-040", "accepted", "ok")]}}
    queue.enqueue(core, job)
    runner = threading.Thread(target=worker.run_once, args=(core, SESSION))
    runner.start()
    assert dispatcher.blocked.wait(10)
    assert approvals(open_core(core.root)) == {}
    assert read.describe(job) == owner_text.STEP_READING
    release.set()
    runner.join(10)
    assert set(approvals(open_core(core.root))) == {"SR-040"}


def test_confirmation_readback_and_show_first_text_pass_the_owner_level_scan(core) -> None:
    assert owner_level(owner_text.CONFIRM_YOU_SAID.format(evidence="ok")) == []
    assert owner_level(owner_text.READBACK_CHANGE.format(
        title="Plain words UX", change="some features stay internal")) == []
    after, applied, _ = run(core, "confirm SR-041", ["SR-040"], [
        entry_of(core, "SR-041", "accepted", "confirm SR-041", hash="")])
    (card,) = applied.cards
    assert owner_level(card.issue) == [] and owner_level(card.topic) == []
    _ = json, files, FakeDispatcher, ctx_for, open_card
