"""SR-169: the gate is the session's, under the one digest the prompt hook logged."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.test_clarify_job import plant_card

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyAnswer, ClarifyQuestion
from plumb.understand import cardstore, clarify, cmd_clarify, effects, gate, hooks, worker

pytestmark = pytest.mark.sr("SR-225")

TEXT = "/plumb clarify let users export their data"  # SR-171: the check runs on the command
CARD = {"intent": "yes", "topic": "exporting", "gap": True,
        "gaps": [{"id": "format", "question": "Which format?", "suggestions": ["csv", "json"],
                  "blocking": True}]}
NO_GAP = {"intent": "yes", "topic": "export", "gap": False, "gaps": []}


def _say(repo: Path, session: str, text: str = TEXT) -> str:
    digest = log_prompt(repo, text, session=session)
    hooks.on_prompt(SimpleNamespace(session_id=session), open_core(repo),
                    {"digest": digest, "text": text})
    return digest


def test_ex1_same_text_in_two_sessions_each_gate_is_its_own(repo: Path,
                                                             engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    _say(repo, "s1")
    worker.run_once(open_core(repo), "s1")
    plant_card(repo, "s1")                                  # a card an agent's question raised
    assert gate.is_closed(repo, "s1")                       # s1's card holds its gate
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    _say(repo, "s2")
    worker.run_once(open_core(repo), "s2")
    assert cmd_clarify.wait(open_core(repo), "s2", timeout=5).state == "ready"
    assert not gate.is_closed(repo, "s2") and gate.is_closed(repo, "s1")


def test_ex2_the_check_reports_and_opens_under_the_hooks_digest(
        repo: Path, engine_standins: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    first = _say(repo, "s1")
    worker.run_once(open_core(repo), "s1")
    log_prompt(repo, "something typed in another session", session="s2")
    log_prompt(repo, '<cross-session-message from="x" from-name="peer">hi</cross-session-message>',
               session="s1")                                # newer, but not the owner's words
    outcome = cmd_clarify.wait(open_core(repo), timeout=5)   # no session named: this one's
    assert outcome.state == "ready" and outcome.digest == first
    (opened,) = [e.payload for e in open_core(repo).events() if e.kind == "gate"]
    assert opened["digest"] == first and not gate.is_closed(repo, "s1")


def test_ex3_answering_the_card_opens_the_gate_with_no_clarify_rerun(
        repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    digest = _say(repo, "s1")
    worker.run_once(open_core(repo), "s1")
    plant_card(repo, "s1")
    (card,) = [c for c in cardstore.own_cards(repo, "s1") if c.id == clarify.choice_id(digest)]
    answered = CardState(**{**card.__dict__, "answers": tuple(
        ClarifyAnswer(q.id, "accepted", digest) for q in card.questions)})
    effects.handler_for("choice")(core=open_core(repo), job=SimpleNamespace(session="s1"),
                                  card=answered, digest=digest)
    assert not gate.is_closed(repo, "s1")
    assert len(engine_standins.dispatcher.ran("clarify")) == 1

