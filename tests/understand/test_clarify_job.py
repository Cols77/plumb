"""SHOW S1 and S6: the clarify job kind (SR-103 EX-1 to EX-4, EX-8, EX-9, EX-12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt, run
from understand.fakes import FakeDispatcher, owner_level

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyAnswer
from plumb.understand import cardstore, clarify, effects, files, gate, worker

pytestmark = pytest.mark.sr("SR-103")

SESSION = "s1"
SR = ("---\nid: SR-001\ntitle: Export users as CSV\nfeature: FEAT-001\n"
      "statement: export the user list as CSV\n"
      "examples:\n- id: EX-1\n  given: 2 users\n  when: exported\n  then: 2 rows\n---\n")


def _gap(ident: str, question: str, recommended: int = 0) -> dict[str, Any]:
    return {"id": ident, "question": question,
            "suggestions": ["the first way", "the second way", "the third way"],
            "recommended": recommended}


def _asked(text: str, answer: dict[str, Any], repo: Path, engine_standins: Any, *,
           after: str | None = None) -> tuple[Any, str]:
    """The owner says ``text``; the prompt hook's side runs, then the worker."""
    core = open_core(repo)
    digest = log_prompt(repo, text, session=SESSION)
    gate.close(repo, SESSION, digest, "your request is being checked")
    engine_standins.dispatcher.script = {"clarify": answer}
    job = clarify.build(core, SESSION, message={"digest": digest, "text": text}, after=after)
    assert job is not None
    worker.run_once(core, SESSION)
    return open_core(repo), digest


def _cards(repo: Path) -> list[CardState]:
    return cardstore.own_cards(repo, SESSION)


def _gate_entries(core: Any) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in core.events() if e.kind == "gate"]


def test_ex1_export_request_one_card_format_and_scope_rest_assumptions(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "exporting user data",
              "readback": {"will": ["let a user download their data"],
                           "wont": ["export other people's data"],
                           "assumptions": ["the file is named after the user",
                                           "only the signed-in user can export"],
                           "examples": ["a user asks for an export and gets one file"]},
              "gaps": [_gap("format", "Which file format should the export use?", 1),
                       _gap("scope", "Which of their data goes in the export?")]}
    core, digest = _asked("let users export their data", answer, repo, engine_standins)
    (card,) = _cards(repo)
    assert card.kind == "clarify" and card.id == clarify.card_id(digest)
    assert [q.id for q in card.questions] == ["format", "scope"]
    assert all(2 <= len(q.resolutions) <= 3 for q in card.questions)
    assert card.questions[0].resolutions[0] == "the second way"    # the recommended one first
    assert [t for t, _ in clarify.assumptions(card)] == [
        "the file is named after the user", "only the signed-in user can export"]
    assert {s for _, s in clarify.assumptions(card)} == {"proposed"}
    assert gate.is_closed(repo, SESSION)
    assert owner_level("\n".join(clarify.render(card))) == []
    assert not _gate_entries(core)


def test_ex2_request_that_maps_to_confirmed_requirement_no_card(
        repo: Path, write_record: Any, engine_standins: Any) -> None:
    write_record(repo, SR)
    assert run(repo, "approve", "SR-001") == 0
    answer = {"intent": "yes", "topic": "export as CSV", "gaps": []}
    core, digest = _asked("export the user list as CSV", answer, repo, engine_standins)
    assert _cards(repo) == []
    sent = engine_standins.dispatcher.jobs[0].inputs
    assert [t["id"] for t in sent["touched"]] == ["SR-001"]
    assert sent["touched"][0]["status"] == "confirmed"
    assert not gate.is_closed(repo, SESSION)
    (entry,) = _gate_entries(core)
    assert entry["state"] == "open" and entry["digest"] == digest and entry["by"] == "clarify"


def test_ex3_five_gaps_offer_a_spec_session(repo: Path, engine_standins: Any) -> None:
    gaps = [_gap(f"g{n}", f"Question number {n}?") for n in range(1, 6)]
    answer = {"intent": "yes", "topic": "a big feature", "gaps": gaps}
    core, _ = _asked("rebuild the billing system", answer, repo, engine_standins)
    (card,) = _cards(repo)
    assert clarify.is_escalation(card)
    assert len(card.questions) == 1 and card.questions[0].id == "spec"
    assert "5" in card.issue
    assert gate.is_closed(repo, SESSION)
    assert owner_level("\n".join(clarify.render(card))) == []


def test_three_gaps_make_one_card_of_three_questions(repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "export", "gaps": [
        _gap("a", "First?"), _gap("b", "Second?"), _gap("c", "Third?")]}
    _asked("export things", answer, repo, engine_standins)
    (card,) = _cards(repo)
    assert not clarify.is_escalation(card) and len(card.questions) == 3


def test_ex4_a_question_carries_no_intent_no_card(repo: Path, engine_standins: Any) -> None:
    core, digest = _asked("what does plumb status show?",
                          {"intent": "no", "gaps": [_gap("x", "Ignored?")]}, repo,
                          engine_standins)
    assert _cards(repo) == []
    assert not gate.is_closed(repo, SESSION)
    assert [e["digest"] for e in _gate_entries(core)] == [digest]


def test_ex8_two_answers_confirmed_assumption_stays_proposed(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "export", "readback": {
        "assumptions": ["the file is named after the user"]},
        "gaps": [_gap("format", "Which format?"), _gap("scope", "Which data?")]}
    core, digest = _asked("let users export their data", answer, repo, engine_standins)
    (card,) = _cards(repo)
    answered = card.__class__(**{**card.__dict__, "status": "answered", "answers": (
        ClarifyAnswer("format", "accepted", "sha256:m2"),
        ClarifyAnswer("scope", "change: only their own profile", "sha256:m2"))})
    handler = effects.handler_for("clarify")
    assert handler is not None
    result = handler(core=core, job=engine_standins.dispatcher.jobs[0], card=answered,
                     digest="sha256:m2", accepted=True, entry={})
    assert result is None or not result.entries           # nothing is confirmed on its behalf
    assert set(clarify.confirmed_answers(answered)) == {"format", "scope"}
    assert clarify.assumptions(answered) == [("the file is named after the user", "proposed")]
    assert not [e for e in core.events() if e.kind == "approval"]


def test_ex9_clarify_job_needs_the_read_job_and_its_inputs_hold_the_answered_card(
        repo: Path, engine_standins: Any) -> None:
    core = open_core(repo)
    first = log_prompt(repo, "let users export their data", session=SESSION)
    asked = {"intent": "yes", "topic": "export",
             "gaps": [_gap("format", "Which format?"), _gap("scope", "Which data?")]}
    _asked("let users export their data", asked, repo, engine_standins)
    (card,) = _cards(repo)
    assert card.id == clarify.card_id(first)
    # the owner answers all of it in one message; the reader (applied first) mapped it
    reply = log_prompt(repo, "csv, and everything about them", session=SESSION)
    mapped = CardState(**{**card.__dict__, "status": "answered", "answers": (
        ClarifyAnswer("format", "change: csv", reply), ClarifyAnswer("scope", "accepted", reply))})
    cardstore.save(repo, SESSION, [mapped])
    gate.close(repo, SESSION, reply, "your request is being checked")
    job = clarify.build(core, SESSION, message={"digest": reply, "text": "csv, and everything"
                                                " about them"}, after="read-0123456789abcdef")
    assert job is not None and job.needs == "read-0123456789abcdef"
    inputs = clarify.recompute(core, job)
    assert inputs is not None
    assert {a["question"] for a in inputs["answered"]} == {"format", "scope"}
    # the model repeats a question the owner just answered, and one new thing it does not ask
    engine_standins.dispatcher.script = {"clarify": {"intent": "yes", "gaps": [
        _gap("format", "Which format?")]}}
    worker.run_once(core, SESSION, job.id)
    assert [c.id for c in _cards(repo) if c.status == "open"] == []     # no second card
    assert not gate.is_closed(repo, SESSION)
    assert [e["digest"] for e in _gate_entries(open_core(repo))] == [reply]


def test_a_late_result_for_an_older_message_never_opens_a_newer_gate(
        repo: Path, engine_standins: Any) -> None:
    old = log_prompt(repo, "add a thing", session=SESSION)
    core = open_core(repo)
    gate.close(repo, SESSION, old, "your request is being checked")
    job = clarify.build(core, SESSION, message={"digest": old, "text": "add a thing"})
    newer = log_prompt(repo, "add another thing", session=SESSION)
    gate.close(repo, SESSION, newer, "your request is being checked")
    engine_standins.dispatcher.script = {"clarify": {"intent": "no"}}
    worker.run_once(core, SESSION, job.id)
    assert gate.is_closed(repo, SESSION)


def test_clarify_registers_clarify_and_couldnt_check() -> None:
    assert effects.handler_for("clarify") is not None
    assert effects.handler_for("couldnt_check") is not None


def test_same_message_same_job_id(repo: Path, engine_standins: Any) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, "add a thing", session=SESSION)
    one = clarify.build(core, SESSION, message={"digest": digest, "text": "add a thing"})
    two = clarify.build(core, SESSION, message={"digest": digest, "text": "add a thing"})
    assert one is not None and two is not None and one.id == two.id
    assert len(list(files.jobs_dir(repo, SESSION).glob("*.json"))) == 1
    assert json.loads(next(files.jobs_dir(repo, SESSION).glob("*.json")).read_text(
        encoding="utf-8"))["kind"] == "clarify"


def test_fake_dispatcher_is_the_one_in_use(engine_standins: Any) -> None:
    assert isinstance(engine_standins.dispatcher, FakeDispatcher)
