"""SHOW S3 (release): a failed check, and the only ways to release it (SR-103 EX-7, EX-10,
EX-11)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.fakes import owner_level

from plumb.api import open_core
from plumb.present import owner_text
from plumb.understand import cardstore, clarify, cmd_clarify, effects, files, fullcard, gate, hooks, worker

pytestmark = pytest.mark.sr("SR-103")

SESSION = "s1"


def _ctx() -> Any:
    return SimpleNamespace(session_id=SESSION)


def _failed_check(repo: Path, engine_standins: Any, text: str = "let users export their data"
                  ) -> tuple[Any, str]:
    """The owner says something; the dispatcher fails; ``--wait`` returns."""
    engine_standins.dispatcher.failing("run", "the model could not be reached")
    core = open_core(repo)
    digest = log_prompt(repo, text, session=SESSION)
    hooks.on_prompt(_ctx(), core, {"digest": digest, "text": text})
    worker.run_once(core, SESSION)
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert outcome.state == "couldnt_check"
    return core, digest


def _entries(repo: Path) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in open_core(repo).events() if e.kind == "gate"]


def test_ex7_dispatcher_failure_couldnt_check_card_nothing_built(
        repo: Path, engine_standins: Any) -> None:
    _, digest = _failed_check(repo, engine_standins)
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "couldnt_check"]
    assert card.id == clarify.couldnt_card_id(digest) and card.status == "open"
    (question,) = card.questions
    assert question.text == "Build without the check?"
    assert question.resolutions == (owner_text.GATE_WAIT, owner_text.GATE_BUILD_ANYWAY)
    assert "Nothing was built" in card.issue
    assert gate.is_closed(repo, SESSION) and not _entries(repo)         # nothing opened it
    assert owner_level(fullcard.render(fullcard.content(open_core(repo), card))) == []
    assert engine_standins.dispatcher.ran("clarify")


def test_release_by_button_typed_go_or_prose_at_threshold_only(
        repo: Path, engine_standins: Any) -> None:
    # the button
    core, digest = _failed_check(repo, engine_standins)
    assert gate.release(core, SESSION, "button")
    assert not gate.is_closed(repo, SESSION)
    assert [e["by"] for e in _entries(repo)] == ["release:button"]
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "couldnt_check"]
    assert card.status == "closed"
    assert gate.release(core, SESSION, "button") is False               # nothing left to release


def test_release_by_the_typed_go_the_prompt_hook_sees(repo: Path, engine_standins: Any) -> None:
    core, digest = _failed_check(repo, engine_standins)
    go = log_prompt(repo, "/plumb go", session=SESSION)
    lines = hooks.on_prompt(_ctx(), open_core(repo), {"digest": go, "text": "/plumb go"})
    assert not gate.is_closed(repo, SESSION)
    assert [e["by"] for e in _entries(repo)] == ["release:typed"]
    assert lines and owner_level("\n".join(lines)) == []
    # the typed go carried no request: it queued no check of its own
    assert len(list(files.jobs_dir(repo, SESSION).glob("clarify-*.json"))) == 1


def test_release_by_prose_only_when_the_reader_accepted_at_the_threshold(
        repo: Path, engine_standins: Any) -> None:
    core, digest = _failed_check(repo, engine_standins)
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "couldnt_check"]
    reply = log_prompt(repo, "yes just build it", session=SESSION)
    handler = effects.handler_for("couldnt_check")
    job = SimpleNamespace(session=SESSION)
    # below the threshold (or answered "wait"): the reader reports accepted=False
    handler(core=core, job=job, card=card, digest=reply, accepted=False,
            entry={"answer": "accepted", "confidence": 0.5})
    assert gate.is_closed(repo, SESSION)
    handler(core=core, job=job, card=card, digest=reply, accepted=True,
            entry={"answer": "accepted", "confidence": 0.95})
    assert not gate.is_closed(repo, SESSION)
    assert [e["by"] for e in _entries(repo)] == ["release:owner-words"]


def test_no_other_route_opens_a_failed_check(repo: Path, engine_standins: Any) -> None:
    core, digest = _failed_check(repo, engine_standins)
    assert gate.release(core, SESSION, "agent") is False
    assert gate.release(core, SESSION, "") is False
    assert gate.open(core, SESSION, "sha256:something-else", "clarify", "x") is False
    # a clarify card's handler does not release a failed check
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "couldnt_check"]
    effects.handler_for("clarify")(core=core, job=SimpleNamespace(session=SESSION), card=card,
                                   digest=digest)
    assert gate.is_closed(repo, SESSION)
    # a gate closed by a card's questions is not a failed check, whatever is typed
    other = log_prompt(repo, "add a thing", session=SESSION)
    gate.close(repo, SESSION, other, "a question about your request is waiting")
    assert gate.release(core, SESSION, "button") is False
    assert gate.is_closed(repo, SESSION) and not _entries(repo)


def test_ex10_no_wait_keeps_gate_closed_next_turn_retries(
        repo: Path, engine_standins: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import queue

    core, digest = _failed_check(repo, engine_standins)
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "couldnt_check"]
    effects.handler_for("couldnt_check")(core=core, job=SimpleNamespace(session=SESSION),
                                         card=card, digest=digest, accepted=False,
                                         entry={"answer": "rejected"})
    assert gate.is_closed(repo, SESSION)
    retried: list[str] = []
    monkeypatch.setattr(queue, "retry_failed", lambda c, session: retried.append(session) or [])
    # the open card makes the turn's read job (it answers nothing), which the check waits for
    engine_standins.dispatcher.script = {"clarify": {"intent": "no", "gap": False, "gaps": []},
                                         "read": {"entries": []}}
    text = "are you there?"
    again = log_prompt(repo, text, session=SESSION)
    hooks.on_prompt(_ctx(), open_core(repo), {"digest": again, "text": text})
    assert retried == [SESSION]                              # the failed check is tried again
    state = gate.state(repo, SESSION)
    assert state.state == "closed" and state.message_digest == again
    worker.run_once(open_core(repo), SESSION)                # and this time it works
    assert not gate.is_closed(repo, SESSION)


def test_ex11_failed_job_for_ok_message_still_refuses_edits(
        repo: Path, engine_standins: Any) -> None:
    _failed_check(repo, engine_standins, text="ok")
    assert gate.is_closed(repo, SESSION)     # the failed model would have said it carried none
    from plumb.hosts.claude_code import pretool

    answer = pretool.decide(repo, SESSION, "Edit")
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
