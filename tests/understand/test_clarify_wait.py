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
from understand.fakes import owner_level

from plumb.api import open_core
from plumb.understand import cardstore, clarify, cmd_clarify, files, gate, hooks, worker

pytestmark = pytest.mark.sr("SR-103")

SESSION = "s1"
CARD = {"intent": "yes", "topic": "exporting data", "gap": True,
        "gaps": [{"id": "format", "question": "Which format?", "suggestions": ["csv", "json"]},
                 {"id": "scope", "question": "Which data?", "suggestions": ["all", "mine"]}]}
NO_GAP = {"intent": "yes", "topic": "export", "gap": False, "gaps": []}


def _say(repo: Path, text: str = "let users export their data") -> tuple[Any, str]:
    core = open_core(repo)
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
    assert any("Which format?" in line for line in outcome.lines)
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
    assert cards["clarify"].status == "open"
    assert len(engine_standins.dispatcher.ran("clarify")) == 1


def test_runs_the_job_itself_when_none_queued(repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    core = open_core(repo)
    digest = log_prompt(repo, "let users export their data", session=SESSION)
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
    log_prompt(repo, "let users export their data", session=SESSION)
    assert cmd_clarify.run("clarify", ["--wait", "--json", "--root", str(repo),
                                       "--timeout", "5"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "card" and data["card"].startswith("clarify:")


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
