"""Approval after a question round, and sets approved whole (task 4 of the judge-approval plan).
A record whose premise holds the owner's question-tool answers at its version is approved citing
them: ``by: auto-jev`` when JEV clears it (a passing calibration, strictly above max(0.9, the
threshold), with or without the fast track), else ``by: auto-model`` when the judge model says
the intent is clear, its confidence logged and never compared. An escalated set is one approval,
written when every record of it is clear. JEV and the model are stubs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.approvals import approval_items
from plumb.confirm import checked
from plumb.understand import judge
from understand import test_judge_cascade
from understand.fakes import FakeDispatcher, as_worker
from understand.test_cascade_fast_track import approvals, asked, judged, verdict_of, write
from understand.test_judge_cascade import StubJev, calibrate_to, configure, fast_track_on
from understand.test_judge_job import (
    MESSAGE,
    SESSION,
    intent_text,
    log_prompt,
    requirement_text,
)

world = test_judge_cascade.world   # INT-001 and SR-001 from the owner's logged MESSAGE

ASK = "Should every page load faster, or only the public ones?"
OPTIONS = [{"label": "Public pages (Recommended)", "description": "Only those."},
           {"label": "Every page", "description": "All of them."}]


def owner_answers(root: Path, ids: list[str], answer: str = "Public pages") -> str:
    """The owner answers the judge's question about ``ids`` with the question tool, as the
    PostToolUse hook logs it; returns the entry's digest."""
    core = open_core(root)
    index = core.index()
    return core.log_append("events", "question-answer", {
        "session": SESSION, "question": ASK, "options": OPTIONS, "answer": answer,
        "via": "question-tool", "asked": {
            "job": "judge-0000000000000000", "key": judge.question_key(ASK),
            "records": [{"id": i, "hash": index[i].hash} for i in ids]}}).digest


def model_says(*items: tuple[str, float, bool]) -> FakeDispatcher:
    """The judge model: ``(id, confidence, clear)`` per record, each supported."""
    return FakeDispatcher({"judge": {"verdicts": [
        {"id": i, "verdict": "supported", "confidence": c, "beyond": [], "contradicts": [],
         "clear": clear} for i, c, clear in items]}})


def state(root: Path, record_id: str) -> tuple[str, str | None]:
    status = open_core(root).status([record_id])[record_id]
    return status.confirmation, status.approved_by


def problems(root: Path) -> list[str]:
    return [why for entry, why in checked(open_core(root))
            if entry.kind == "approval" and why]


def reported(root: Path, record_id: str) -> list[Any]:
    from plumb.validate import validate

    return [f for f in validate(open_core(root)) if f.subject == record_id
            or record_id in f.message]


# ---- SR-248 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-248")
def test_ex4_after_the_answers_jev_at_0_95_approves_with_both_verdicts_and_the_answers(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-4: fast track on and calibrated, JEV 0.7: the model is asked; the owner
    answers and JEV judges again at 0.95: approved by auto-jev, both verdicts logged and the
    answer kept with the question it answered."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    first = model_says(("SR-001", 0.6, False))
    _, _, applied = judged(core, ["SR-001"], StubJev(0.7), first)
    assert approvals(applied) == [] and asked(first) == ["SR-001"]
    write(world, applied)
    digest = owner_answers(world, ["SR-001"])
    again = FakeDispatcher()
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.95), again)
    [approval] = approvals(applied)
    assert approval["by"] == "auto-jev" and approval["auto"]["score"] == 0.95
    assert approval["answers"] == [digest] and again.jobs == []      # no further question
    write(world, applied)
    assert state(world, "SR-001") == ("confirmed", "auto-jev")
    core = open_core(world)
    assert [e.payload["jev_score"] for e in core.events()
            if e.kind == "verdict" and e.payload["id"] == "SR-001"] == [0.7, 0.95]
    [answer] = [e.payload for e in core.events() if e.digest == digest]
    assert answer["question"] == ASK and answer["answer"] == "Public pages"


@pytest.mark.sr("SR-248")
def test_ex5_jev_0_85_and_haiku_clear_at_0_8_approves_by_auto_model(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-5: after the answers JEV scores 0.85 and the judge model (haiku) says the
    intent is clear at 0.8: approved by auto-model (haiku, 0.8), no further question."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    owner_answers(world, ["SR-001"])
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.85),
                           model_says(("SR-001", 0.8, True)))
    [approval] = approvals(applied)
    assert approval["by"] == "auto-model"
    assert (approval["auto"]["model"], approval["auto"]["confidence"],
            approval["auto"]["clear"]) == ("haiku", 0.8, True)
    write(world, applied)
    assert state(world, "SR-001") == ("confirmed", "auto-model")
    assert judge.open_questions(open_core(world), SESSION) == []


@pytest.mark.sr("SR-248")
def test_without_calibration_jev_at_0_92_approves_nothing_and_the_model_decides(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No calibration, an answer and JEV 0.92: no auto-jev; the model is asked and decides."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    configure(world)
    owner_answers(world, ["SR-001"])
    model = model_says(("SR-001", 0.7, True))
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.92), model)
    assert asked(model) == ["SR-001"]
    logged = verdict_of(applied, "SR-001")
    assert logged["jev_score"] == 0.92 and logged["jev_clears"] is False
    assert [a["by"] for a in approvals(applied)] == ["auto-model"]


# ---- SR-209 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-209")
def test_ex1_the_validated_requirement_is_approved_citing_the_owners_words(
        world: Path) -> None:
    """SR-209 EX-1: the owner's message is in the prompt log and the judge validates the
    requirement against it after the owner's answer: approved on the owner's behalf, citing
    the owner's message and their answer (the pre-intent entry comes with task 6)."""
    digest = owner_answers(world, ["SR-001"])
    core = open_core(world)
    _, _, applied = judged(core, ["SR-001"], None, model_says(("SR-001", 0.9, True)))
    [approval] = approvals(applied)
    message = hashlib.sha256(MESSAGE.encode("utf-8")).hexdigest()
    assert approval["prompt_digest"] == f"sha256:{message}"
    assert approval["answers"] == [digest] and approval["session"] == SESSION
    write(world, applied)
    assert state(world, "SR-001") == ("confirmed", "auto-model")
    assert problems(world) == []


# ---- SR-251 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-251")
def test_ex2_an_auto_jev_approval_at_0_6_is_refused_and_the_record_stays_proposed(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-251 EX-2: a worker wrote a by: auto-jev approval at 0.6, under the 0.9 floor: it is
    refused, SR-001 counts as proposed and plumb validate reports the inert entry."""
    core = configure(world)
    calibrate_to(core, 0.43)
    digest = owner_answers(world, ["SR-001"])
    core = open_core(world)
    calibration = next(e for e in core.events() if e.kind == "calibration")
    with as_worker(world, SESSION):
        core.log_append("events", "approval", {
            "records": approval_items(core, ["SR-001"]), "by": "auto-jev",
            "prompt_digest": digest, "answers": [digest], "session": SESSION, "job": "j",
            "auto": {"score": 0.6, "confidence_label": "high", "judge": "jev",
                     "model_version": "jev-1", "calibration": calibration.digest,
                     "claim_kind": "example-restatement", "threshold": 0.43}})
    [why] = problems(world)
    assert "not above" in why
    assert state(world, "SR-001") == ("proposed", None)
    assert reported(world, "SR-001")


# ---- SR-210 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-210")
def test_ex3_an_owner_quoted_approval_written_by_hand_is_not_accepted(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-210 EX-3: the agent writes an approval by hand with an owner quote (on a host that
    cannot mark its session): it is not accepted and validation reports it."""
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    core = open_core(world)
    core.log_append("events", "approval", {
        "records": approval_items(core, ["SR-001"]), "by": "owner",
        "prompt_digest": None, "quote": "yes, approve the two-second rule", "quote_digest": None})
    [why] = problems(world)
    assert "by hand" in why
    assert state(world, "SR-001") == ("proposed", None)
    assert reported(world, "SR-001")


@pytest.mark.sr("SR-210")
def test_ex3_a_study_room_approval_with_no_question_at_that_version_is_not_accepted(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-210 EX-3: an entry saying the owner answered in the study room, with no question
    put at that version: not accepted, and validation reports it."""
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    core = open_core(world)
    core.log_append("events", "approval", {
        "records": approval_items(core, ["SR-001"]), "by": "study-room",
        "prompt_digest": None, "quote": "approved in the study room"})
    assert problems(world)
    assert state(world, "SR-001") == ("proposed", None)
    assert reported(world, "SR-001")


# ---- sets ---------------------------------------------------------------------------------


@pytest.fixture
def escalated(repo: Path, write_record) -> Path:
    """INT-001 is an escalated spec; SR-001 and SR-002 derive from it (its set)."""
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "I want pages to load faster", "Make pages load faster",
                                   prompt=digest).replace("mode: incremental",
                                                          "mode: escalated"))
    for n in (1, 2):
        write_record(repo, requirement_text(
            n, f"Pages rule {n}", f"Public pages follow rule {n}", intent=1,
            examples=((f"page {n}", "it is requested", f"rule {n} holds"),)))
    return repo


@pytest.mark.sr("SR-248")
def test_a_set_with_one_record_unclear_approves_nothing_then_whole(escalated: Path) -> None:
    """A set is approved whole (P6): with SR-002 unclear nothing is approved and the clear
    records wait for their set; once every record is clear, one approval names the set."""
    from plumb.capture.spec import set_state

    ids = ["INT-001", "SR-001", "SR-002"]
    owner_answers(escalated, ids)
    _, _, applied = judged(open_core(escalated), ids, None, model_says(
        ("INT-001", 0.9, True), ("SR-001", 0.9, True), ("SR-002", 0.9, False)))
    assert approvals(applied) == []
    assert any("waits for its set" in n for n in applied.notes)
    write(escalated, applied)
    assert {state(escalated, i)[0] for i in ids} == {"proposed"}
    _, _, applied = judged(open_core(escalated), ["SR-002"], None,
                           model_says(("SR-002", 0.7, True)))
    [approval] = approvals(applied)
    assert approval["by"] == "auto-model" and approval["auto"]["confidence"] == 0.7
    assert {r["id"] for r in approval["records"]} == set(ids)
    assert approval["set"]["anchor"] == "INT-001"
    write(escalated, applied)
    assert {state(escalated, i) for i in ids} == {("confirmed", "auto-model")}
    assert set_state(open_core(escalated), "INT-001") == "approved"
    assert problems(escalated) == []
