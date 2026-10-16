"""SHOW S2: the gate that holds a build until the owner answers (SR-103)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.fakes import owner_level

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyAnswer, ClarifyQuestion, GateState
from plumb.understand import cardstore, clarify, effects, files, gate, hooks, worker

pytestmark = pytest.mark.sr("SR-223")

SESSION = "s1"


def _ctx() -> Any:
    return SimpleNamespace(session_id=SESSION)


def _say(repo: Path, text: str) -> tuple[Any, str]:
    core = open_core(repo)
    text = "/plumb clarify " + text      # SR-171: only the command runs the check
    digest = log_prompt(repo, text, session=SESSION)
    lines = hooks.on_prompt(_ctx(), core, {"digest": digest, "text": text})
    assert all(owner_level(line) == [] or "plumb" not in line for line in lines)
    return core, digest


def _jobs(repo: Path) -> list[str]:
    return sorted(p.stem for p in files.jobs_dir(repo, SESSION).glob("clarify-*.json"))


def test_prompt_hook_closes_gate_and_queues_clarify_job(repo: Path,
                                                        engine_standins: Any) -> None:
    core, digest = _say(repo, "let users export their data")
    state = gate.state(repo, SESSION)
    assert state.state == "closed" and state.message_digest == digest
    assert gate.is_closed(repo, SESSION)
    (job_id,) = _jobs(repo)
    # the hook did not wait for it: nothing ran
    assert not files.results_dir(repo, SESSION).exists() or not list(
        files.results_dir(repo, SESSION).glob("*.json"))
    # the same message again queues nothing new
    hooks.on_prompt(_ctx(), core, {"digest": digest, "text": "/plumb clarify let users export their data"})
    assert _jobs(repo) == [job_id]


def test_hook_gives_the_clarify_job_the_read_job_as_needs(repo: Path, engine_standins: Any,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import read

    monkeypatch.setattr(read, "on_prompt", lambda ctx, core, entry: "read-0123456789abcdef")
    _say(repo, "let users export their data")
    (job_id,) = _jobs(repo)
    raw = files.read_json(files.jobs_dir(repo, SESSION) / f"{job_id}.json")
    assert raw["needs"] == "read-0123456789abcdef"


def test_opens_on_no_intent(repo: Path, engine_standins: Any) -> None:
    core, digest = _say(repo, "what does plumb status show?")
    engine_standins.dispatcher.script = {"clarify": {"intent": "no", "gap": False, "gaps": []}}
    worker.run_once(core, SESSION)
    assert not gate.is_closed(repo, SESSION)
    (entry,) = [e.payload for e in open_core(repo).events() if e.kind == "gate"]
    assert entry["digest"] == digest and entry["state"] == "open"


def _card(digest: str, answered: list[str]) -> CardState:
    questions = (ClarifyQuestion("format", "Which format?", ("csv", "json")),
                 ClarifyQuestion("scope", "Which data?", ("all", "profile")))
    answers = tuple(ClarifyAnswer(q, "accepted", digest) for q in answered)
    return CardState(id="choice:old", kind="choice", topic="export", issue="two things",
                     questions=questions, answers=answers,
                     status="answered" if len(answered) == 2 else "open")


def test_opens_when_card_fully_answered(repo: Path) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, "csv and everything", session=SESSION)
    gate.close(repo, SESSION, digest, "your request is being checked")
    job = SimpleNamespace(session=SESSION)
    handler = effects.handler_for("choice")
    handler(core=core, job=job, card=_card(digest, ["format"]), digest=digest)
    assert gate.is_closed(repo, SESSION)                    # one of two questions mapped
    handler(core=core, job=job, card=_card(digest, ["format", "scope"]), digest=digest)
    assert not gate.is_closed(repo, SESSION)
    assert [e.payload["by"] for e in open_core(repo).events() if e.kind == "gate"] == ["clarify"]


def test_a_rejected_answer_does_not_open_the_gate(repo: Path) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, "neither", session=SESSION)
    gate.close(repo, SESSION, digest, "x")
    card = _card(digest, ["format", "scope"])
    card = CardState(**{**card.__dict__, "answers": (
        ClarifyAnswer("format", "accepted", digest), ClarifyAnswer("scope", "rejected", digest))})
    effects.handler_for("choice")(core=core, job=SimpleNamespace(session=SESSION), card=card,
                                   digest=digest)
    assert gate.is_closed(repo, SESSION)


def test_stays_closed_with_a_pending_job(repo: Path, engine_standins: Any) -> None:
    core, digest = _say(repo, "csv and everything")
    handler = effects.handler_for("choice")
    handler(core=core, job=SimpleNamespace(session=SESSION),
            card=_card(digest, ["format", "scope"]), digest=digest)
    assert gate.is_closed(repo, SESSION)       # this message's clarify job has still to run
    assert _jobs(repo)


def test_open_without_log_entry_reported(repo: Path) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, "add a thing", session=SESSION)
    gate.close(repo, SESSION, digest, "x")
    assert gate.problems(core) == []                        # closed is not a problem
    # someone writes the file open without plumb opening it
    files.write_json_atomic(files.gate_path(repo, SESSION), files.gate_to_json(
        GateState(state="open", message_digest=digest, reason="by hand")))
    found = gate.problems(open_core(repo))
    assert len(found) == 1 and SESSION in found[0] and owner_level(found[0]) == []
    # plumb's own opening leaves no problem
    gate.close(repo, SESSION, digest, "x")
    assert gate.open(open_core(repo), SESSION, digest, "clarify", "nothing is unclear")
    assert gate.problems(open_core(repo)) == []


def test_validate_reports_a_gate_opened_by_hand(repo: Path) -> None:
    from plumb.validate import validate

    digest = log_prompt(repo, "add a thing", session=SESSION)
    files.write_json_atomic(files.gate_path(repo, SESSION), files.gate_to_json(
        GateState(state="open", message_digest=digest, reason="by hand")))
    problems = validate(open_core(repo))
    assert any(SESSION in str(p) for p in problems)


def test_a_gate_closed_for_a_newer_message_is_not_opened_for_an_older_one(repo: Path) -> None:
    core = open_core(repo)
    gate.close(repo, SESSION, "sha256:new", "x")
    assert gate.open(core, SESSION, "sha256:old", "clarify", "late") is False
    assert gate.is_closed(repo, SESSION)


def test_a_session_with_no_gate_file_is_open(tmp_path: Path) -> None:
    assert gate.is_closed(tmp_path, "nobody") is False
    assert clarify.GO_TEXT.match("/plumb go") and not clarify.GO_TEXT.match("/plumb go now")
    assert cardstore.own_cards(tmp_path, "nobody") == []
