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
from plumb.understand import judge, verdict
from understand import test_judge_cascade
from understand.fakes import FakeDispatcher, as_worker
from understand.test_cascade_fast_track import (
    approvals,
    asked,
    build_job,
    judged,
    verdict_of,
    write,
)
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


@pytest.mark.sr("SR-209")
def test_ex4_a_typed_answer_still_counts_once_the_record_is_reworded_to_agree(
        world: Path, monkeypatch: pytest.MonkeyPatch, write_record: Any) -> None:
    """SR-209 EX-4: the owner types their own answer (not an option) to the judge's question;
    the agent rewords the requirement to agree, so its hash changes; the judge's next round
    is shown that answer with the reworded record and approves citing it, instead of asking
    the same question again."""
    from plumb.understand import premise

    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    before = core.index()["SR-001"].hash
    digest = owner_answers(world, ["SR-001"], answer="Every page, the admin ones too")
    write_record(world, requirement_text(
        1, "Pages load in two seconds", "Every page loads within two seconds", intent=1,
        examples=(("any page", "it is requested", "it loads within 2 seconds"),)))
    core = open_core(world)
    record = core.index()["SR-001"]
    assert record.hash != before
    assert [e.digest for e in premise.answer_entries(core, record)] == [digest]
    assert premise.premise_of(core, record).answers[0]["answer"] == \
        "Every page, the admin ones too"
    _, _, applied = judged(core, ["SR-001"], StubJev(0.85), model_says(("SR-001", 0.8, True)))
    [approval] = approvals(applied)
    assert approval["by"] == "auto-model" and approval["answers"] == [digest]
    write(world, applied)
    assert state(world, "SR-001") == ("confirmed", "auto-model")


@pytest.mark.sr("SR-248")
def test_ex9_an_answer_the_record_was_confirmed_on_does_not_carry_a_later_edit(
        world: Path, monkeypatch: pytest.MonkeyPatch, write_record: Any) -> None:
    """SR-248 EX-9 beside SR-209 EX-4: once the record is confirmed on the owner's answer, an
    edit of it is a new version the answer was never about: the judge's premise holds no
    answer, nothing is approved on it, and a forged approval citing it is refused."""
    from plumb.understand import premise

    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    digest = owner_answers(world, ["SR-001"])
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.85),
                           model_says(("SR-001", 0.8, True)))
    write(world, applied)
    assert state(world, "SR-001") == ("confirmed", "auto-model")
    write_record(world, requirement_text(
        1, "Pages load in two seconds", "Every page loads within two seconds", intent=1,
        examples=(("any page", "it is requested", "it loads within 2 seconds"),)))
    core = open_core(world)
    record = core.index()["SR-001"]
    assert premise.answer_entries(core, record) == []
    _, _, applied = judged(core, ["SR-001"], StubJev(0.85), model_says(("SR-001", 0.8, True)))
    assert approvals(applied) == []
    with as_worker(world, SESSION):
        core.log_append("events", "approval", {
            "records": approval_items(core, ["SR-001"]), "by": "auto-model",
            "prompt_digest": "sha256:x", "job": "judge-2", "answers": [digest],
            "auto": {"model": "haiku", "confidence": 0.9, "clear": True}})
    assert any("unconfirmed earlier one" in why for why in problems(world))
    assert state(world, "SR-001")[0] == "unconfirmed-edit"     # the forged entry changed nothing


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
def test_without_calibration_jev_at_0_92_approves_after_the_round(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DEC-143: no calibration, an answer and JEV 0.92: above the 0.9 floor, JEV approves
    after the round and the model is not asked."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    configure(world)
    owner_answers(world, ["SR-001"])
    model = model_says(("SR-001", 0.7, True))
    _, _, applied = judged(open_core(world), ["SR-001"], StubJev(0.92), model)
    assert asked(model) == []
    logged = verdict_of(applied, "SR-001")
    assert logged["jev_score"] == 0.92 and logged["jev_clears"] is True
    assert [a["by"] for a in approvals(applied)] == ["auto-jev"]


@pytest.mark.sr("SR-248")
@pytest.mark.parametrize("by", ["model", "jev"])
def test_a_contradicts_verdict_carrying_a_clearing_jev_score_approves_nothing(
        world: Path, monkeypatch: pytest.MonkeyPatch, by: str) -> None:
    """After a round, a verdict that is not supported (here the model's or JEV's
    contradiction) approves nothing, even when it carries a JEV mapping that clears."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    owner_answers(world, ["SR-001"])
    job, done, _ = judged(open_core(world), ["SR-001"], StubJev(0.95), FakeDispatcher())
    [raw] = done.answer["verdicts"]
    assert raw["jev"]["clears"]
    forged = {**done.answer, "verdicts": [{**raw, "by": by, "verdict": "contradicts",
                                           "contradicts": ["every page, not public ones"],
                                           "clear": True}]}
    applied = judge.apply(open_core(world), job, forged)
    assert approvals(applied) == []


@pytest.mark.sr("SR-248")
def test_an_answer_logged_after_the_job_was_built_approves_nothing(world: Path) -> None:
    """The judge was shown answer A; answer B about the same version is logged before the
    verdict is applied: the verdict cites A only and approves nothing (B is judged next)."""
    first = owner_answers(world, ["SR-001"])
    model = model_says(("SR-001", 0.9, True))
    core = open_core(world)
    job = build_job(core, ["SR-001"])
    done = verdict.cascade(core, job, system="judge", schema={}, jev=None, dispatcher=model)
    owner_answers(world, ["SR-001"], answer="Every page")
    applied = judge.apply(open_core(world), job, done.answer)
    assert approvals(applied) == []
    assert verdict_of(applied, "SR-001")["answers"] == [first]
    assert any("not shown" in n for n in applied.notes)


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
@pytest.mark.parametrize("source", [{"by": "study-room"}, {"by": "owner", "via": "study-room"}])
def test_ex3_a_study_room_approval_with_no_question_at_that_version_is_not_accepted(
        world: Path, monkeypatch: pytest.MonkeyPatch, source: dict[str, str]) -> None:
    """SR-210 EX-3: an entry saying the owner answered in the study room, with no question
    put at that version: not accepted, and validation reports it."""
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    core = open_core(world)
    core.log_append("events", "approval", {
        "records": approval_items(core, ["SR-001"]), **source,
        "prompt_digest": None, "quote": None})
    [why] = problems(world)
    assert "no question put at that version" in why
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


def test_an_answer_to_the_agents_own_question_reaches_the_judge_of_the_same_session(
        world: Path) -> None:
    """Case report-4c7b844d: the owner answered the agent's own question (no judge question,
    so no ``asked``) in the session that spoke the record's message; the judge of the record,
    wherever it runs, is shown that answer instead of asking it again."""
    from plumb.understand import premise

    digest = open_core(world).log_append("events", "question-answer", {
        "session": SESSION, "question": "Build it now or only review it?",
        "options": OPTIONS, "answer": "Build it now", "via": "question-tool"}).digest
    core = open_core(world)
    record = core.index()["SR-001"]
    assert [e.digest for e in premise.answer_entries(core, record)] == [digest]
