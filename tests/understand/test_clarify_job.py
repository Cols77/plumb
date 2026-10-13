"""SHOW S1 and S6: the clarify job kind (SR-103 EX-1 to EX-4, EX-8, EX-9, EX-12)."""

from __future__ import annotations

import dataclasses

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


def _gap(ident: str, question: str, recommended: int = 0, **more: Any) -> dict[str, Any]:
    return {"id": ident, "question": question,
            "suggestions": ["the first way", "the second way", "the third way"],
            "consequences": ["costs a day", "costs an hour", "costs a week"],
            "recommended": recommended, **more}


def _asked(text: str, answer: dict[str, Any], repo: Path, engine_standins: Any, *,
           after: str | None = None) -> tuple[Any, str]:
    """The owner says ``text``; the prompt hook's side runs, then the worker."""
    core = open_core(repo)
    digest = log_prompt(repo, text, session=SESSION)
    gate.close(repo, SESSION, digest, "your request is being checked")
    # the real worker checks the answer against the schema: it always carries the gap flag
    engine_standins.dispatcher.script = {"clarify": {"gap": bool(answer.get("gaps")),
                                                     "gaps": [], **answer}}
    job = clarify.build(core, SESSION, message={"digest": digest, "text": text}, after=after)
    assert job is not None
    worker.run_once(core, SESSION)
    return open_core(repo), digest


def _cards(repo: Path) -> list[CardState]:
    return cardstore.own_cards(repo, SESSION)


def _by_kind(repo: Path, kind: str) -> list[CardState]:
    return [c for c in _cards(repo) if c.kind == kind and c.status == "open"]


def _gate_entries(core: Any) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in core.events() if e.kind == "gate"]


def _text(card: CardState) -> str:
    return "\n".join([card.topic, card.issue, card.evidence,
                      *(q.text for q in card.questions), *card.resolutions])


def test_sr131_ex2_one_blocking_choice_the_rest_assumptions(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "exporting user data",
              "readback": {"proposal": "Let a user download their data as one file.",
                           "will": ["let a user download their data"],
                           "wont": ["export other people's data", "send it by mail"],
                           "assumptions": ["the file is named after the user"],
                           "examples": ["a user asks for an export and gets one file"]},
              "gaps": [_gap("format", "Which file format should the export use?", 1,
                            blocking=True, diagram=False),
                       _gap("scope", "Which of their data goes in the export?")]}
    core, digest = _asked("let users export their data", answer, repo, engine_standins)
    (readback,) = _by_kind(repo, "clarify")
    assert readback.id == clarify.card_id(digest)
    assert readback.issue == "Let a user download their data as one file."
    assert readback.topic.startswith("Your request of ")
    assert readback.topic.endswith('"let users export their data"')
    assert [t for t, _ in clarify.assumptions(readback)] == [
        "the file is named after the user",
        "Which of their data goes in the export?: the first way"]
    assert readback.evidence.splitlines()[-1] == "Not doing: export other people's data"
    assert "send it by mail" not in readback.evidence          # at most one won't
    assert [c.label for c in readback.questions[0].choices] == ["Yes, that is what I meant", "Not quite"]
    (choice,) = _by_kind(repo, "choice")
    assert choice.id == clarify.choice_id(digest) and choice.issue.startswith("Which file")
    assert choice.questions[0].resolutions[0] == "the second way"    # the recommended one first
    assert [c.consequence for c in choice.questions[0].choices][0] == "costs an hour"
    assert choice.evidence.startswith("What changes: ") and choice.diagram == ""
    assert gate.is_closed(repo, SESSION)
    assert owner_level(_text(readback) + _text(choice)) == []
    assert not _gate_entries(core)


def test_sr131_ex3_three_gaps_with_recommendations_are_assumptions_and_no_card(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "export", "gaps": [
        _gap("a", "First?"), _gap("b", "Second?"), _gap("c", "Third?")]}
    core, digest = _asked("export things", answer, repo, engine_standins)
    (readback,) = _cards(repo)
    assert [t for t, _ in clarify.assumptions(readback)] == [
        "First?: the first way", "Second?: the first way", "Third?: the first way"]
    assert not gate.is_closed(repo, SESSION)
    assert [e["digest"] for e in _gate_entries(core)] == [digest]


def test_sr131_ex1_a_resolved_reference_is_an_assumption_and_the_work_starts(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "the findings", "readback": {
        "proposal": "Fix every finding listed above.",
        "assumptions": ["the findings are the ones I listed above"]}}
    _asked("resolve all the findings using a workflow", answer, repo, engine_standins)
    assert _by_kind(repo, "choice") == [] and not gate.is_closed(repo, SESSION)


def test_sr146_ex1_a_structure_question_names_a_diagram_file(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "host file", "gaps": [
        _gap("writer", "Which of the three hooks should write host.json?", blocking=True,
             diagram=True)]}
    _, digest = _asked("write host.json somewhere", answer, repo, engine_standins)
    (choice,) = _by_kind(repo, "choice")
    assert choice.diagram == f".plumb/session/{SESSION}/diagrams/{clarify.short(digest)}.html"


def test_sr146_ex2_a_wording_question_gets_no_diagram(repo: Path,
                                                      engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "findings", "gaps": [
        _gap("which", "Does the word findings mean the ones listed above?", blocking=True,
             diagram=False)]}
    _asked("fix the findings", answer, repo, engine_standins)
    (choice,) = _by_kind(repo, "choice")
    assert choice.diagram == ""


def test_sr131_two_blocking_gaps_offer_a_spec_session_not_a_guess(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "x", "gaps": [
        _gap("a", "First?", blocking=True), _gap("b", "Second?", blocking=True)]}
    _asked("do two things", answer, repo, engine_standins)
    (choice,) = _by_kind(repo, "choice")
    assert clarify.is_escalation(choice)
    assert "Assumed: " not in _by_kind(repo, "clarify")[0].evidence


def test_sr132_ex1_a_newer_read_back_withdraws_the_card_it_replaces(
        repo: Path, engine_standins: Any) -> None:
    gaps = [_gap("which", "Which findings should I resolve?", blocking=True)]
    _, old = _asked("resolve the findings", {"intent": "yes", "topic": "findings",
                                             "gaps": gaps}, repo, engine_standins)
    older = clarify.choice_id(old)
    assert [c.id for c in _by_kind(repo, "choice")] == [older]
    _, new = _asked("resolve findings 1 and 2", {"intent": "yes", "topic": "findings",
                                                 "replaces": [older, "nonesuch"]},
                    repo, engine_standins)
    by_id = {c.id: c for c in _cards(repo)}
    assert by_id[older].status == "withdrawn"
    assert [c.id for c in _by_kind(repo, "choice")] == []
    assert by_id[clarify.card_id(new)].status == "open"
    sent = engine_standins.dispatcher.jobs[-1].inputs
    assert [c["id"] for c in sent["open_cards"]] == [clarify.card_id(old), older]


def test_ex2_request_that_maps_to_confirmed_requirement_no_choice(
        repo: Path, write_record: Any, engine_standins: Any) -> None:
    write_record(repo, SR)
    assert run(repo, "approve", "SR-001") == 0
    answer = {"intent": "yes", "topic": "export as CSV", "gaps": []}
    core, digest = _asked("export the user list as CSV", answer, repo, engine_standins)
    assert [c.kind for c in _cards(repo)] == ["clarify"]
    sent = engine_standins.dispatcher.jobs[0].inputs
    assert [t["id"] for t in sent["touched"]] == ["SR-001"]
    assert sent["touched"][0]["status"] == "confirmed"
    assert not gate.is_closed(repo, SESSION)
    (entry,) = _gate_entries(core)
    assert entry["state"] == "open" and entry["digest"] == digest and entry["by"] == "clarify"


def test_ex3_five_gaps_offer_a_spec_session(repo: Path, engine_standins: Any) -> None:
    gaps = [_gap(f"g{n}", f"Question number {n}?", blocking=True) for n in range(1, 6)]
    answer = {"intent": "yes", "topic": "a big feature", "gaps": gaps}
    core, _ = _asked("rebuild the billing system", answer, repo, engine_standins)
    (card,) = _by_kind(repo, "choice")
    assert clarify.is_escalation(card)
    assert len(card.questions) == 1 and card.questions[0].id == "spec"
    assert [c.answer for c in card.questions[0].choices] == ["change", "accepted"]
    assert "5" in card.issue
    assert gate.is_closed(repo, SESSION)
    assert owner_level(_text(card)) == []


def test_sr131_many_gaps_with_a_recommendation_are_assumed_not_asked(
        repo: Path, engine_standins: Any) -> None:
    gaps = [_gap(f"g{n}", f"Question number {n}?") for n in range(1, 6)]
    answer = {"intent": "yes", "topic": "a big feature", "gaps": gaps}
    _asked("rebuild the billing system", answer, repo, engine_standins)
    assert _by_kind(repo, "choice") == []
    (card,) = _by_kind(repo, "clarify")
    assert card.evidence.count("Assumed:") >= 5
    assert not gate.is_closed(repo, SESSION)


def test_ex4_a_question_carries_no_intent_no_card(repo: Path, engine_standins: Any) -> None:
    core, digest = _asked("what does plumb status show?",
                          {"intent": "no", "gaps": [_gap("x", "Ignored?")]}, repo,
                          engine_standins)
    assert _cards(repo) == []
    assert not gate.is_closed(repo, SESSION)
    assert [e["digest"] for e in _gate_entries(core)] == [digest]


def _request(repo: Path, write_record: Any, digest: str) -> None:
    """An intent of the request, two requirements and a decision on one of them."""
    write_record(repo, "\n".join([
        "---", "id: INT-001", "title: Export", "quote: export",
        "prompt: " + clarify.short(digest), "---", ""]))
    for n in (1, 2):
        write_record(repo, "\n".join([
            "---", f"id: SR-00{n}", f"title: Export {n}", "feature: FEAT-001",
            f"statement: export {n}", "links:", "- kind: derives_from", "  to: INT-001",
            "examples:", "- id: EX-1", "  given: a", "  when: b", "  then: c", "---", ""]))
    write_record(repo, "\n".join([
        "---", "id: DEC-001", "title: Format", "question: Which format?", "chosen: csv",
        "links:", "- kind: decides", "  to: SR-001", "---", ""]))


def test_sr130_ex1_an_ok_on_the_read_back_confirms_the_whole_request(
        repo: Path, write_record: Any, engine_standins: Any) -> None:
    core, digest = _asked("let users export", {"intent": "yes", "topic": "export"}, repo,
                          engine_standins)
    _request(repo, write_record, digest)
    core = open_core(repo)
    (card,) = _by_kind(repo, "clarify")
    answered = CardState(**{**card.__dict__, "status": "answered", "answers": (
        ClarifyAnswer(clarify.READBACK_ID, "accepted", digest),)})
    confirmed: list[str] = []
    handler = effects.handler_for("clarify")
    assert handler is not None
    assert handler(core=core, card=answered, digest=digest, accepted=False,
                   confirm=lambda *a, **k: confirmed.append(a[0])) is None
    assert confirmed == []                                   # not quite confirms nothing
    handler(core=core, card=answered, digest=digest, accepted=True,
            confirm=lambda *a, **k: confirmed.append(a[0]))
    assert confirmed == ["DEC-001", "INT-001", "SR-001", "SR-002"]


def test_ex8_a_choice_answer_confirms_nothing_and_opens_the_gate(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "export", "gaps": [
        _gap("format", "Which format?", blocking=True)]}
    core, digest = _asked("let users export their data", answer, repo, engine_standins)
    (card,) = _by_kind(repo, "choice")
    answered = card.__class__(**{**card.__dict__, "status": "answered", "answers": (
        ClarifyAnswer("format", "change: the first way", "sha256:m2"),)})
    handler = effects.handler_for("choice")
    assert handler is not None
    result = handler(core=core, job=engine_standins.dispatcher.jobs[0], card=answered,
                     digest="sha256:m2", accepted=True, entry={})
    assert result is None or not result.entries           # nothing is confirmed on its behalf
    assert set(clarify.confirmed_answers(answered)) == {"format"}
    assert not [e for e in core.events() if e.kind == "approval"]


def test_ex9_clarify_job_needs_the_read_job_and_its_inputs_hold_the_answered_card(
        repo: Path, engine_standins: Any) -> None:
    core = open_core(repo)
    first = log_prompt(repo, "let users export their data", session=SESSION)
    asked = {"intent": "yes", "topic": "export",
             "gaps": [_gap("format", "Which format?", blocking=True)]}
    _asked("let users export their data", asked, repo, engine_standins)
    (card,) = _by_kind(repo, "choice")
    assert card.id == clarify.choice_id(first)
    # the owner answers it in a message; the reader (applied first) mapped it
    reply = log_prompt(repo, "csv", session=SESSION)
    mapped = CardState(**{**card.__dict__, "status": "answered", "answers": (
        ClarifyAnswer("format", "change: csv", reply),)})
    cardstore.save(repo, SESSION, [mapped])
    gate.close(repo, SESSION, reply, "your request is being checked")
    job = clarify.build(core, SESSION, message={"digest": reply, "text": "csv"},
                        after="read-0123456789abcdef")
    assert job is not None and job.needs == "read-0123456789abcdef"
    inputs = clarify.recompute(core, job)
    assert inputs is not None
    assert {a["question"] for a in inputs["answered"]} == {"format"}
    # the model repeats a question the owner just answered
    engine_standins.dispatcher.script = {"clarify": {"intent": "yes", "gap": True, "gaps": [
        _gap("format", "Which format?", blocking=True)]}}
    worker.run_once(core, SESSION, job.id)
    assert _by_kind(repo, "choice") == []                               # no second question
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


# ---------------------------------------------------------------- S6: the clarifier's cases


def test_evalset_clarify_cases_load_and_run_on_the_fake() -> None:
    from plumb.understand import evalrun

    cases = evalrun.load_cases("clarify")
    assert len(cases) >= 12
    quiet = [c for c in cases if not c["expect"]["gap"]]
    gappy = [c for c in cases if c["expect"]["gap"]]
    assert len(quiet) >= 10                                  # requests that need no clarification
    texts = {c["inputs"]["message"]["text"] for c in gappy}
    assert "let users export their data" in texts
    five = [c for c in gappy if len(c.get("known_gaps") or ()) == 5]
    assert five, "a request with five known gaps"
    for case in cases:
        message = case["inputs"]["message"]
        import hashlib

        assert message["digest"] == "sha256:" + hashlib.sha256(
            message["text"].encode("utf-8")).hexdigest()      # frozen copies, digest honest
        assert set(case["expect"]) == {"intent", "gap"}
        assert (case["expect"]["intent"] == "no") <= (not case["expect"]["gap"])
    results = evalrun.run_cases(evalrun.FakeEvalDispatcher(), cases, "clarify")
    assert len(results) == len(cases) and all(r["passed"] for r in results)
    assert not any(r["false_gap"] for r in results)


class _AlwaysAsks:
    """A clarifier that asks about everything: every question on a quiet request is a false gap."""

    name = "asks-everything"

    def available(self) -> None:
        return None

    def run(self, job: Any, **_: Any) -> dict[str, Any]:
        return {"intent": "yes", "gap": True, "gaps": [_gap("x", "Really?")]}


def test_ex12_false_gap_rate_measured_and_reported_with_calibration_results(
        repo: Path) -> None:
    from plumb.understand import evalrun

    cases = evalrun.load_cases("clarify")
    quiet = sum(1 for c in cases if not c["expect"]["gap"])
    results = evalrun.run_cases(_AlwaysAsks(), cases, "clarify")
    assert sum(r["false_gap"] for r in results) == quiet     # measured: the questions that
    # change nothing about what gets built
    assert evalrun.run("eval", ["--fake", "--root", str(repo)]) == 0
    entries = [dict(e.payload) for e in open_core(repo).events() if e.kind == "eval-run"]
    (entry,) = entries
    assert entry["false_gap_rate"] == 0.0                    # reported beside the results
    assert entry["cases"] and entry["passed"] == len(entry["cases"])
    assert any(c["kind"] == "clarify" for c in entry["cases"])


def test_the_schema_and_the_agent_ask_for_the_gap_flag_and_the_list() -> None:
    assert clarify.schema["id"] == "clarify.v1"
    assert set(clarify.schema["required"]) == {"intent", "gap", "gaps"}
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(
        encoding="utf-8")
    assert "false gap" not in prompt and "changes nothing" in prompt


def _offer_answered(repo: Path, engine_standins: Any, label: str) -> tuple[Any, str]:
    """Two blocking gaps; the owner presses ``label`` on the spec session offer."""
    from plumb.understand import answer

    answer_ = {"intent": "yes", "topic": "x", "gaps": [
        _gap("a", "First?", blocking=True), _gap("b", "Second?", blocking=True)]}
    core, digest = _asked("do two things", answer_, repo, engine_standins)
    (choice,) = _by_kind(repo, "choice")
    pick = next(c for c in choice.questions[0].choices if c.label == label)
    job = clarify.build(core, SESSION, message={"digest": digest, "text": "do two things"})
    work = answer.Answering(core, SESSION, job=job, digest=digest)
    answer.apply_answer(work, card=choice.id, question="spec", record="", hash="", choice=pick,
                        source=answer.Button(offer_id="o", key_digest="sha256:k"))
    applied = work.applied()
    new = {c.id: c for c in applied.cards}
    cardstore.save(repo, SESSION, [new.get(c.id, c) for c in _cards(repo)])
    return core, digest


def test_sr131_no_to_the_spec_session_opens_the_gate_and_lists_the_guesses(
        repo: Path, engine_standins: Any) -> None:
    _offer_answered(repo, engine_standins, clarify.SPEC_NO)
    assert not gate.is_closed(repo, SESSION)
    (request,) = _by_kind(repo, "clarify")
    assert "Assumed: First?: the first way" in request.evidence
    assert "Assumed: Second?: the first way" in request.evidence


def test_sr131_yes_to_the_spec_session_keeps_the_gate_closed(
        repo: Path, engine_standins: Any) -> None:
    _offer_answered(repo, engine_standins, clarify.SPEC_YES)
    assert gate.is_closed(repo, SESSION)


@pytest.mark.sr("SR-131")
def test_sr131_ex4_a_vague_answer_keeps_the_choice_card_and_opens_no_read_back(
        repo: Path, engine_standins: Any) -> None:
    gaps = {"intent": "yes", "topic": "export", "gaps": [
        _gap("format", "Which format?", blocking=True)]}
    core, _ = _asked("let users export their data", gaps, repo, engine_standins)
    (card,) = _by_kind(repo, "choice")
    before = [(c.id, c.status) for c in _cards(repo)]
    digest = log_prompt(repo, "whatever works", session=SESSION)
    gate.close(repo, SESSION, digest, "your request is being checked")
    core.log_append("events", "read-entry", {   # the reader found it answers the card, no pick
        "job": "r1", "id": f"{card.id}/format", "hash": "", "answer": "open",
        "confidence": 0.9, "evidence": "whatever works", "message_digest": digest})
    # as live: the read job applies first and leaves the card left_open
    cardstore.save(repo, SESSION, [dataclasses.replace(c, status="left_open") if c.id == card.id
                                   else c for c in cardstore.own_cards(repo, SESSION)])
    before = [(c.id, c.status) for c in _cards(repo)]
    engine_standins.dispatcher.script = {"clarify": {
        "gap": False, "gaps": [], "intent": "yes", "topic": "export", "replaces": [card.id],
        "readback": {"proposal": "Export in any format.", "will": [], "wont": [],
                     "assumptions": [], "examples": []}}}
    assert clarify.build(open_core(repo), SESSION, message={"digest": digest,
                                                            "text": "whatever works"})
    worker.run_once(open_core(repo), SESSION)
    assert [(c.id, c.status) for c in _cards(repo)] == before    # nothing withdrawn, nothing new
    assert gate.is_closed(repo, SESSION)
