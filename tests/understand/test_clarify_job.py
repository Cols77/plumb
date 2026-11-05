"""SHOW S1 and S6: the clarify job kind (SR-103 EX-1 to EX-4, EX-8, EX-9, EX-12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.fakes import FakeDispatcher, owner_level

from plumb import approvals
from plumb.api import open_core
from plumb.understand import clarify, files, gate, worker

pytestmark = pytest.mark.sr("SR-223")

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


def _cards(repo: Path) -> list[str]:
    """Any card file in the session folder: none is ever written (SR-382)."""
    return sorted(p.name for p in files.session_dir(repo, SESSION).glob("*cards*.json"))


def _gate_entries(core: Any) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in core.events() if e.kind == "gate"]


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
    (asked,) = clarify.gap_questions(core, SESSION)
    assert asked["question"].startswith("Which file")
    assert [o["label"] for o in asked["options"]][0] == "the second way"   # recommended first
    assert [o["description"] for o in asked["options"]][0] == "costs an hour"
    assert not gate.is_closed(repo, SESSION)          # outside the loop no question holds
    assert owner_level(asked["question"]) == []


@pytest.mark.parametrize("n", [2, 3, 5])
def test_sr223_ex15_every_blocking_gap_is_asked_at_once_never_a_card_or_spec_session(
        repo: Path, engine_standins: Any, n: int) -> None:
    """SR-223 EX-15: two or more gaps with no better-supported option are all asked in the
    same turn with the question tool; no card, no spec session, no limit per turn."""
    gaps = [_gap(f"g{i}", f"Question number {i}?", blocking=True) for i in range(1, n + 1)]
    core, _ = _asked("rebuild the billing system",
                     {"intent": "yes", "topic": "billing", "gaps": gaps}, repo, engine_standins)
    assert _cards(repo) == []
    assert [q["question"] for q in clarify.gap_questions(core, SESSION)] == [
        f"Question number {i}?" for i in range(1, n + 1)]
    assert not gate.is_closed(repo, SESSION)


def test_sr223_ex15_a_gap_the_owner_answered_is_not_asked_again(
        repo: Path, engine_standins: Any) -> None:
    gaps = [_gap("a", "First?", blocking=True), _gap("b", "Second?", blocking=True)]
    core, _ = _asked("do two things", {"intent": "yes", "topic": "x", "gaps": gaps},
                     repo, engine_standins)
    core.log_append("events", "question-answer", {
        "session": SESSION, "question": "First? (Recommended)", "options": [],
        "answer": "the first way", "message_digest": "sha256:x"})
    assert [q["question"] for q in clarify.gap_questions(open_core(repo), SESSION)] == [
        "Second?"]


def test_sr131_ex3_three_gaps_with_recommendations_are_assumptions_and_no_card(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "export", "gaps": [
        _gap("a", "First?"), _gap("b", "Second?"), _gap("c", "Third?")]}
    core, digest = _asked("export things", answer, repo, engine_standins)
    assert not gate.is_closed(repo, SESSION)
    assert [e["digest"] for e in _gate_entries(core)] == [digest]


def _flag(repo: Path, text: str, subject: str = "SR-001") -> str:
    """The prompt hook's flag: this request may change the confirmed ``subject``."""
    import hashlib

    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = repo / ".plumb" / "session" / "intent_flags.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"session": SESSION, "prompt_digest": digest,
                                 "subject": subject}) + "\n")
    return digest


SR1 = """---
id: SR-001
title: add adds
feature: FEAT-001
statement: add(a, b) returns the sum of a and b.
examples:
- id: EX-1
  given: the numbers 1 and 2
  when: add(1, 2) is called
  then: it returns 3
---
"""


def test_sr225_ex1_a_flagged_request_keeps_the_gate_closed_naming_the_example(
        repo: Path, engine_standins: Any, write_record) -> None:
    write_record(repo, SR1)
    text = "make add subtract instead"
    _flag(repo, text)
    answer = {"intent": "yes", "topic": "add", "readback": {"proposal": "make add subtract"}}
    _asked(text, answer, repo, engine_standins)
    state = gate.state(repo, SESSION)
    assert state.state == "closed" and state.reason == "intent change: SR-001 EX-1"


def test_sr225_ex7_a_flagged_question_never_closes_the_gate(
        repo: Path, engine_standins: Any, write_record) -> None:
    write_record(repo, SR1)
    text = "why does add return 3 here?"
    _flag(repo, text)
    _asked(text, {"intent": "no", "topic": "add"}, repo, engine_standins)
    assert not gate.is_closed(repo, SESSION)


def test_sr225_ex4_no_hold_when_the_loop_ran_for_this_request(
        repo: Path, engine_standins: Any, write_record) -> None:
    write_record(repo, SR1)
    text = "make add subtract instead"
    digest = _flag(repo, text)
    loop = files.session_dir(repo, SESSION) / "intent" / f"{digest[7:19]}.json"
    loop.parent.mkdir(parents=True, exist_ok=True)
    loop.write_text("{}", encoding="utf-8")
    answer = {"intent": "yes", "topic": "add", "readback": {"proposal": "make add subtract"}}
    _asked(text, answer, repo, engine_standins)
    assert not gate.is_closed(repo, SESSION)


def test_sr131_ex1_a_resolved_reference_is_an_assumption_and_the_work_starts(
        repo: Path, engine_standins: Any) -> None:
    answer = {"intent": "yes", "topic": "the findings", "readback": {
        "proposal": "Fix every finding listed above.",
        "assumptions": ["the findings are the ones I listed above"]}}
    _asked("resolve all the findings using a workflow", answer, repo, engine_standins)
    assert not gate.is_closed(repo, SESSION)


def test_ex2_request_that_maps_to_confirmed_requirement_no_choice(
        repo: Path, write_record: Any, engine_standins: Any) -> None:
    write_record(repo, SR)
    approvals.approve(open_core(repo), ["SR-001"])
    answer = {"intent": "yes", "topic": "export as CSV", "gaps": []}
    core, digest = _asked("export the user list as CSV", answer, repo, engine_standins)
    sent = engine_standins.dispatcher.jobs[0].inputs
    assert [t["id"] for t in sent["touched"]] == ["SR-001"]
    assert sent["touched"][0]["status"] == "confirmed"
    assert not gate.is_closed(repo, SESSION)
    (entry,) = _gate_entries(core)
    assert entry["state"] == "open" and entry["digest"] == digest and entry["by"] == "clarify"


def test_sr131_many_gaps_with_a_recommendation_are_assumed_not_asked(
        repo: Path, engine_standins: Any) -> None:
    gaps = [_gap(f"g{n}", f"Question number {n}?") for n in range(1, 6)]
    answer = {"intent": "yes", "topic": "a big feature", "gaps": gaps}
    _asked("rebuild the billing system", answer, repo, engine_standins)
    assert not gate.is_closed(repo, SESSION)


def test_ex4_a_question_carries_no_intent_no_card(repo: Path, engine_standins: Any) -> None:
    core, digest = _asked("what does plumb status show?",
                          {"intent": "no", "gaps": [_gap("x", "Ignored?")]}, repo,
                          engine_standins)
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


@pytest.mark.sr("SR-223")
def test_sr154_operating_the_tools_is_not_a_request() -> None:
    """Only a change to the repository's own system raises a card (the model is told so)."""
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(
        encoding="utf-8")
    assert "this repository's own" in prompt and "Operating the tools or the machine is" in prompt
