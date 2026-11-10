"""SR-169: the gate is the session's, under the one digest the prompt hook logged."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from iaso.api import open_core
from iaso.understand import cmd_clarify, gate, hooks, worker

pytestmark = pytest.mark.sr("SR-225")

TEXT = "/iaso clarify let users export their data"  # SR-171: the check runs on the command
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
    digest = _say(repo, "s1")
    worker.run_once(open_core(repo), "s1")
    gate.close(repo, "s1", digest, "your request is being checked")   # s1's gate only
    assert gate.is_closed(repo, "s1")
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

