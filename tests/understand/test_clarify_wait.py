"""SHOW S3 (wait) and S5 (the skill): ``plumb clarify --wait`` (SR-103 EX-5, EX-6)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from plumb.api import open_core
from plumb.understand import cardstore, clarify, cmd_clarify, files, gate, hooks, worker
from understand.fakes import owner_level

pytestmark = pytest.mark.sr("SR-223")

SESSION = "s1"
CARD = {"intent": "yes", "topic": "exporting data", "gap": True,
        "gaps": [{"id": "format", "question": "Which format?", "suggestions": ["csv", "json"],
                  "consequences": ["opens in a sheet", "needs a program"], "blocking": True},
                 {"id": "scope", "question": "Which data?", "suggestions": ["all", "mine"]}]}
NO_GAP = {"intent": "yes", "topic": "export", "gap": False, "gaps": []}


def _say(repo: Path, text: str = "let users export their data") -> tuple[Any, str]:
    core = open_core(repo)
    text = "/plumb clarify " + text      # SR-171: only the command runs the check
    digest = log_prompt(repo, text, session=SESSION)
    hooks.on_prompt(SimpleNamespace(session_id=SESSION), core, {"digest": digest, "text": text})
    return core, digest


def _work_later(core: Any, delay: float = 0.3) -> threading.Thread:
    done = threading.Thread(target=lambda: (time.sleep(delay), worker.run_once(core, SESSION)))
    done.start()
    return done


def test_ex5_wait_blocks_until_card_ready(repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    gate_event = threading.Event()
    engine_standins.dispatcher.block = gate_event
    core, digest = _say(repo)
    assert gate.is_closed(repo, SESSION)                    # edits are refused meanwhile
    thread = _work_later(core)
    releaser = threading.Timer(0.8, gate_event.set)
    releaser.start()
    started = time.monotonic()
    outcome = cmd_clarify.wait(core, SESSION, timeout=20)
    took = time.monotonic() - started
    thread.join(10)
    releaser.join(10)
    assert took >= 0.7                                      # it really waited for the job
    assert outcome.state == "card" and outcome.digest == digest
    assert outcome.lines == [cmd_clarify.ASK]             # the question is on the card only
    assert outcome.card == clarify.choice_id(digest)
    assert owner_level("\n".join(outcome.lines)) == []
    assert gate.is_closed(repo, SESSION)                    # the card is not answered yet
    assert len(engine_standins.dispatcher.ran("clarify")) == 1


def test_wait_returns_ready_at_once_when_nothing_is_unclear(repo: Path,
                                                            engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    core, _ = _say(repo)
    worker.run_once(core, SESSION)
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert outcome.state == "ready" and not gate.is_closed(repo, SESSION)


def test_ex6_late_result_collected_by_next_wait_no_build_started(
        repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    release = threading.Event()
    engine_standins.dispatcher.block = release
    core, digest = _say(repo)
    runner = threading.Thread(target=lambda: worker.run_once(core, SESSION))
    runner.start()
    assert engine_standins.dispatcher.blocked.wait(10)
    first = cmd_clarify.wait(core, SESSION, timeout=0.3)    # the check is still running
    assert first.state == "couldnt_check"
    (shown,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "couldnt_check"]
    assert shown.status == "open" and gate.is_closed(repo, SESSION)    # no build started
    release.set()
    runner.join(10)
    assert gate.is_closed(repo, SESSION)                    # the late result is a card
    second = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert second.state == "card" and second.digest == digest
    cards = {c.kind: c for c in cardstore.own_cards(repo, SESSION)}
    assert cards["couldnt_check"].status == "closed"        # the late result replaced it
    assert cards["choice"].status == "open" and "clarify" not in cards   # no read-back card
    assert len(engine_standins.dispatcher.ran("clarify")) == 1


def test_runs_the_job_itself_when_none_queued(repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    core = open_core(repo)
    digest = log_prompt(repo, "/plumb clarify let users export their data", session=SESSION)
    assert not list(files.jobs_dir(repo, SESSION).glob("*.json"))
    outcome = cmd_clarify.wait(core, SESSION, timeout=5)
    assert outcome.state == "card" and outcome.digest == digest
    assert len(engine_standins.dispatcher.ran("clarify")) == 1
    assert gate.is_closed(repo, SESSION)                    # closed for it, though no hook ran


def test_same_job_never_runs_twice(repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    core, _ = _say(repo)
    worker.run_once(core, SESSION)
    for _ in range(3):
        outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
        assert outcome.state == "card"
    assert len(engine_standins.dispatcher.ran("clarify")) == 1
    assert len(list(files.jobs_dir(repo, SESSION).glob("clarify-*.json"))) == 1


def test_a_result_with_no_ledger_entry_counts_for_nothing(repo: Path,
                                                          engine_standins: Any) -> None:
    core, digest = _say(repo)
    (job,) = [files.job_from_json(files.read_json(p))
              for p in files.jobs_dir(repo, SESSION).glob("clarify-*.json")]
    files.write_json_atomic(files.results_dir(repo, SESSION) / f"{job.id}.json", {
        "v": 1, "job": job.id, "status": "ok", "answer": {"intent": "no"}, "error": None})
    outcome = cmd_clarify.wait(core, SESSION, timeout=0.2)    # forged by the agent
    assert outcome.state == "couldnt_check" and gate.is_closed(repo, SESSION)


def test_the_command_prints_the_result_as_json(repo: Path, engine_standins: Any,
                                               capsys: pytest.CaptureFixture) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    log_prompt(repo, "/plumb clarify let users export their data", session=SESSION)
    assert cmd_clarify.run("clarify", ["--wait", "--json", "--root", str(repo),
                                       "--timeout", "5"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "card" and data["card"].startswith("choice:")


def test_without_wait_the_command_is_todays_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.capture import cli as capture_cli

    seen: list[list[str]] = []
    monkeypatch.setattr(capture_cli, "run", lambda command, argv: seen.append(argv) or 0)
    assert cmd_clarify.run("clarify", ["add", "multiply"]) == 0
    assert seen == [["add", "multiply"]]


def test_a_typed_go_is_not_a_request_to_check(repo: Path, engine_standins: Any) -> None:
    core, digest = _say(repo)
    log_prompt(repo, "/plumb go", session=SESSION)
    logged = cmd_clarify.latest_prompt(core, SESSION)
    assert logged is not None and logged["digest"] == digest
    assert clarify.is_typed_go("/plumb go") and not clarify.is_typed_go("go")


def test_skill_first_action_is_clarify_wait(repo: Path) -> None:
    from plumb.hosts.claude_code.install import install

    install(repo, launcher="path", commit_hook=False)
    text = (repo / ".claude" / "skills" / "plumb-clarify" / "SKILL.md").read_text(
        encoding="utf-8")
    body = text.split("---", 2)[2]
    opening = body.split("# plumb-clarify", 1)[1].strip().split("\n\n")
    first = " ".join(opening[0:2])
    assert "first action" in first and "plumb clarify --wait" in first
    assert "do not build" in first.lower() and "answered" in first
    assert "{plumb}" not in text
    # what the command returns, and what to do with each outcome
    for words in ("couldn't check", "Build anyway", "spec session", "ready"):
        assert words.lower() in text.lower(), words
    assert "plumb go" not in text.replace("`/plumb go`", "")      # the agent never types it


@pytest.mark.sr("SR-122")
def test_a_finished_check_that_left_no_card_is_not_waiting_for_ever(
        repo: Path, engine_standins: Any) -> None:
    """SR-122 EX-1: the result is in and ok, yet the gate stays closed and no card is open:
    once the limit passes the answer is couldn't check, never "waiting" again (the skill runs
    --wait again on waiting, so it would loop)."""
    engine_standins.dispatcher.script = {"clarify": CARD}
    core, digest = _say(repo)
    worker.run_once(core, SESSION)
    from dataclasses import replace

    # the card closed some other way, the gate left closed
    cardstore.save(repo, SESSION, [replace(c, status="closed")
                                   for c in cardstore.own_cards(repo, SESSION)])
    assert gate.is_closed(repo, SESSION)
    states = {cmd_clarify.wait(open_core(repo), SESSION, timeout=0.2).state for _ in range(2)}
    assert "waiting" not in states


def test_a_request_with_no_blocking_choice_is_ready_and_draws_no_read_back(
        repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": {
        **NO_GAP, "readback": {"assumptions": ["the file is named after the user"]},
        "gap": True, "gaps": [{"id": "scope", "question": "Which data?",
                               "suggestions": ["all", "mine"]}]}}
    core, _ = _say(repo)
    worker.run_once(core, SESSION)
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert outcome.state == "ready" and not gate.is_closed(repo, SESSION)
    assert outcome.lines == [cmd_clarify.READY]
    assert cardstore.own_cards(repo, SESSION) == []      # SR-252 EX-6: no read-back card


def test_a_structure_question_tells_the_agent_to_draw_first(repo: Path,
                                                            engine_standins: Any) -> None:
    gap = {**CARD["gaps"][0], "diagram": True}
    engine_standins.dispatcher.script = {"clarify": {**CARD, "gaps": [gap]}}
    core, digest = _say(repo)
    worker.run_once(core, SESSION)
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    path = f".plumb/session/{SESSION}/diagrams/{clarify.short(digest)}.html"
    assert path in outcome.lines[0] and outcome.lines[0].startswith("Draw the answer space")
    assert CARD["gaps"][0]["question"] in outcome.lines[0]      # what to draw is in the line
    assert outcome.lines[1] == cmd_clarify.ASK


def test_sr131_ex4_an_earlier_blocking_card_is_the_answer_not_a_failed_check(
        repo: Path) -> None:
    """A later message while an earlier choice card holds the gate: --wait names that card
    instead of raising a 'couldn't check' card."""
    from plumb.contracts import CardState

    core = open_core(repo)
    older = CardState(id="choice:aaaaaaaaaaaa", kind="choice", topic="t", issue="Which one?",
                      resolutions=("A", "B"), status="left_open")
    cardstore.save(repo, SESSION, [older])
    digest = log_prompt(repo, "/plumb clarify whatever works", session=SESSION)
    gate.close(repo, SESSION, digest, "a question waits on a card")
    outcome = cmd_clarify._outcome_from_state(core, SESSION, digest)
    assert (outcome.state, outcome.card) == ("card", older.id)


def test_sr131_ex4_answering_the_held_card_opens_the_later_messages_gate(repo: Path) -> None:
    """The choice card of an earlier message held the gate for a later vague message; once
    its question is answered, the gate opens for that later message."""
    from plumb.contracts import CardState, ClarifyAnswer, ClarifyQuestion

    core = open_core(repo)
    first = log_prompt(repo, "/plumb clarify sort the rows, ask me about ties", session=SESSION)
    later = log_prompt(repo, "/plumb clarify whatever works", session=SESSION)
    gate.close(repo, SESSION, later, "a question waits on a card")
    card = CardState(id="choice:" + first.removeprefix("sha256:")[:12], kind="choice",
                     topic="t", issue="Ties?", resolutions=("Keep order", "By id"),
                     questions=(ClarifyQuestion(id="ties", text="Ties?"),),
                     answers=(ClarifyAnswer(question="ties", answer="accepted"),),
                     status="answered")
    cardstore.save(repo, SESSION, [card])
    clarify._choice_effect(core=core, card=card, job=SimpleNamespace(session=SESSION),
                           digest=first)
    assert not gate.is_closed(repo, SESSION)
