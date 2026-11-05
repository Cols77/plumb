"""R2/R3: applying the reader's answers after exact checks only (SR-101). A shown record the
reading covers is confirmed by nothing here: the message is kept as a pre-intent naming it and
a judge job reads them together (task 6 of the judge-approval plan, SR-209 EX-2)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.log import append, stream_of
from plumb.present import owner_text
from plumb.understand import read
from understand.fakes import FakeDispatcher, as_worker, owner_level
from understand.test_read_job import (
    SESSION,
    ctx_for,
    int_text,
    log_prompt,
    make_core,
    record_text,
    state,
)

pytestmark = pytest.mark.sr("SR-214")


def write_applied(core, applied) -> None:
    """What the worker does with an ``Applied``: its log entries (as the worker)."""
    with as_worker(core.root, SESSION):
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


def covered(core) -> dict[str, str]:
    """Record id -> version that the message's pre-intent (``via: read``) names."""
    return {r["id"]: r["hash"] for e in entries_of(core, "pre-intent")
            if e.payload.get("via") == "read" for r in e.payload["asked"]["records"]}


def judge_jobs(core) -> list[list[str]]:
    from plumb.understand import jobs

    return [list(j.inputs["records"]) for j in jobs.queued(core.root, SESSION)
            if j.kind == "judge"]


@pytest.fixture
def core(repo: Path, write_record):
    texts = [int_text(8, "Internal features"), record_text(88, "Plain words UX"),
             int_text(24, "Reminder timing"), record_text(97), record_text(98),
             record_text(40), record_text(41), record_text(2), record_text(3)]
    return make_core(repo, write_record, texts)


def test_ex1_int008_ok_and_sr088_change_both_go_to_the_judge_with_the_words(core) -> None:
    message = ("INT-008 ok, I am not sure I agree with SR-088. In terms of UX, some features "
               "might have to remain internal to plumb.")
    after, applied, job = run(core, message, ["INT-008", "SR-088"], [
        entry_of(core, "INT-008", "accepted", "INT-008 ok"),
        entry_of(core, "SR-088", "change", "some features might have to remain internal to plumb",
                 change="some features stay internal to plumb")])
    assert approvals(after) == {}
    index = core.index()
    assert covered(after) == {i: index[i].hash for i in ("INT-008", "SR-088")}
    (kept,) = entries_of(after, "pre-intent")
    assert kept.payload["text"] == message
    assert kept.payload["source"] == job.inputs["message"]["digest"]
    assert kept.payload["asked"]["job"] == job.id
    assert judge_jobs(after) == [["INT-008", "SR-088"]]


def test_ex2_int24_read_as_int024_all_three_judged(core) -> None:
    message = "Confirm SR-097, SR-098, INT-24"
    after, _, _ = run(core, message, ["SR-097", "SR-098", "INT-024"], [
        entry_of(core, "SR-097", "accepted", "Confirm SR-097"),
        entry_of(core, "SR-098", "accepted", "SR-098"),
        entry_of(core, "INT-24", "accepted", "INT-24")])
    assert set(covered(after)) == {"SR-097", "SR-098", "INT-024"}
    assert approvals(after) == {}


def test_ex3_unshown_record_is_noted_and_confirmed_by_nothing(core) -> None:
    after, applied, _ = run(core, "ok, and confirm SR-041 too", ["SR-040"], [
        entry_of(core, "SR-040", "accepted", "ok"),
        entry_of(core, "SR-041", "accepted", "confirm SR-041 too", hash="")])
    assert set(covered(after)) == {"SR-040"} and approvals(after) == {}
    assert any("SR-041" in note for note in applied.notes)


def test_ex4_confidence_below_threshold_confirms_nothing(core) -> None:
    after, _, _ = run(core, "ok", ["SR-040"], [
        entry_of(core, "SR-040", "accepted", "ok", confidence=0.7)])
    assert approvals(after) == {}
    assert [e.payload["confidence"] for e in entries_of(after, "read-entry")] == [0.7]


def test_ex5_edited_record_confirms_nothing_and_is_noted(core, repo, write_record) -> None:
    def edit():
        write_record(repo, record_text(40, "Plain words UX reworded"))

    after, applied, _ = run(core, "ok", ["SR-040", "SR-041"], [
        entry_of(core, "SR-040", "accepted", "ok"),
        entry_of(core, "SR-041", "accepted", "ok")], edit=edit)
    assert set(covered(after)) == {"SR-041"} and approvals(after) == {}
    assert any("SR-040" in note for note in applied.notes)


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
    assert applied.entries == ()
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


def test_confirmation_lines_say_nothing_was_confirmed_by_the_reading(core) -> None:
    after, _, job = run(core, "INT-008 ok", ["INT-008"], [
        entry_of(core, "INT-008", "accepted", "INT-008 ok")])
    assert read.confirmation_lines(after, job.inputs["message"]["digest"]) == []


def test_ex13_nothing_confirmed_while_the_job_runs_judged_when_it_returns(
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
    assert covered(open_core(core.root)) == {}
    release.set()
    runner.join(10)
    after = open_core(core.root)
    assert set(covered(after)) == {"SR-040"} and approvals(after) == {}


def test_confirmation_text_passes_the_owner_level_scan(core) -> None:
    assert owner_level(owner_text.CONFIRM_YOU_SAID.format(evidence="ok")) == []
    _ = FakeDispatcher, ctx_for


def _forge(core, record_id: str, **changes) -> None:
    """An owner-words approval written the way the worker writes it, then altered."""
    from plumb.approvals import prompt_digest

    message = changes.pop("message", "SR-040 ok")
    payload = {"by": "owner-words", "session": SESSION, "job": "read-0123456789abcdef",
               "records": [{"id": record_id, "hash": core.index()[record_id].hash}],
               "prompt_digest": prompt_digest(message), "message": message,
               "evidence": "SR-040 ok", "confidence": 0.95, **changes}
    if payload["prompt_digest"] not in {e.payload.get("digest") for e in core.events()
                                        if e.kind == "prompt"}:
        core.log_append("events", "prompt", {"digest": payload["prompt_digest"],
                                             "session": SESSION, "at": "2026-10-10T10:00:00Z"})
    with as_worker(core.root, SESSION):
        core.log_append("events", "approval", payload)


def test_recheck_owner_words_catches_forged_entry(core) -> None:
    from plumb.confirm import checked

    _forge(core, "SR-040")                                         # a true entry
    _forge(core, "SR-041", evidence="yes, definitely")             # evidence not in message
    _forge(core, "SR-002", message="SR-040 ok", prompt_digest="sha256:" + "0" * 64)
    _forge(core, "SR-003", confidence=7)                           # not a confidence
    after = open_core(core.root)
    status = after.status(["SR-040", "SR-041", "SR-002", "SR-003"])
    assert status["SR-040"].confirmation == "confirmed"
    assert {i: status[i].confirmation for i in ("SR-041", "SR-002", "SR-003")} == {
        "SR-041": "proposed", "SR-002": "proposed", "SR-003": "proposed"}
    problems = [p for _, p in checked(after) if p]
    assert len(problems) == 3
