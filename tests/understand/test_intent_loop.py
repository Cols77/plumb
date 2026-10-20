"""The intent loop's commands and state (SR-193, SR-194, SR-197): ``plumb intent open``, ``gate``,
``done`` and ``status``."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from plumb.api import open_core
from plumb.capture import proof
from plumb.contracts import Target
from plumb.understand import clarify, cmd_intent, files, gate, hooks, typed, worker
from understand.test_read_job import int_text, record_text

pytestmark = pytest.mark.sr("SR-222")

SESSION = "s1"
WORDS = "add multiply next to add"
NO_GAP = {"intent": "yes", "topic": "multiply", "gap": False, "gaps": []}
DIGEST = "sha256:" + "a" * 64


def _say(repo: Path, text: str) -> str:
    core = open_core(repo)
    digest = log_prompt(repo, text, session=SESSION)
    hooks.on_prompt(SimpleNamespace(session_id=SESSION), core, {"digest": digest, "text": text})
    return digest


def _jobs(repo: Path) -> list[str]:
    return sorted(p.stem for p in files.jobs_dir(repo, SESSION).glob("*.json"))


def _run(repo: Path, *argv: str) -> int:
    return cmd_intent.run("intent", [*argv, "--root", str(repo), "--session", SESSION])


def _findings(tmp_path: Path, *levels: str) -> str:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps([{"level": lv, "what": f"a {lv} finding"} for lv in levels]))
    return str(path)


@pytest.fixture
def intent(repo: Path, write_record: Any) -> Path:
    """INT-001 with the requirement SR-040 deriving from it, and an open loop."""
    write_record(repo, int_text(1))
    write_record(repo, record_text(40))
    open_core(repo).add_link("SR-040", "derives_from", Target(record="INT-001"))
    cmd_intent.open_loop(repo, SESSION, DIGEST)
    return repo


def _loop(repo: Path) -> dict[str, Any]:
    return files.read_json(cmd_intent.loop_path(repo, SESSION, DIGEST))


def test_ex1_the_typed_command_is_checked_and_opens_the_loop(repo: Path, engine_standins: Any,
                                                             capsys: pytest.CaptureFixture) -> None:
    text = "/plumb intent " + WORDS
    assert typed.parse(text) == typed.Typed("intent", words=WORDS)
    assert clarify.commanded_words(text) == WORDS
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    digest = _say(repo, text)
    assert [j for j in _jobs(repo) if j.startswith("clarify-")] and gate.is_closed(repo, SESSION)
    worker.run_once(open_core(repo), SESSION)
    assert _run(repo, "open", "--wait", "--timeout", "5") == 0
    loop = files.read_json(cmd_intent.loop_path(repo, SESSION, digest))
    assert loop["digest"] == digest and loop["intent"] is None
    assert {s: v["state"] for s, v in loop["stages"].items()} == {
        "clarify": "open", "plan": "open", "build": "open"}
    assert "intent loop open" in capsys.readouterr().out
    assert not list((repo / ".plumb" / "intents").glob("*.md"))   # no record until it is clear


def test_a_later_bare_slash_command_does_not_lose_the_loop(repo: Path,
                                                           engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    digest = _say(repo, "/plumb:plumb-intent " + WORDS)
    worker.run_once(open_core(repo), SESSION)
    log_prompt(repo, "/reload-plugins", session=SESSION)
    assert _run(repo, "open", "--wait", "--timeout", "5") == 0
    assert cmd_intent.loop_path(repo, SESSION, digest).exists()


def test_ex4_an_ordinary_message_opens_no_loop_and_runs_no_model(repo: Path,
                                                                  engine_standins: Any) -> None:
    _say(repo, "make the status line show the branch name")
    assert _jobs(repo) == [] and not gate.is_closed(repo, SESSION)
    assert _run(repo, "open") == 0
    assert not list((files.session_dir(repo, SESSION) / "intent").glob("*.json"))
    assert engine_standins.dispatcher.ran("clarify") == []


@pytest.mark.sr("SR-222")
def test_sr194_ex1_the_plan_gate_refuses_while_clarify_has_not_passed(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    none = _findings(tmp_path)
    assert _run(intent, "gate", "plan", "--intent", "INT-001", "--findings", none) == 1
    assert "the clarify gate has not passed" in capsys.readouterr().err
    assert _loop(intent)["stages"]["plan"] == {"state": "open"}


@pytest.mark.sr("SR-222")
def test_sr194_ex2_a_passed_clarify_gate_lets_the_plan_stage_run_and_records_it(
        intent: Path, tmp_path: Path) -> None:
    gate.close(intent, SESSION, DIGEST, gate.INTENT_CHANGE + " SR-040 SR-040/EX-1")
    high = _findings(tmp_path, "high", "low")
    assert _run(intent, "gate", "clarify", "--intent", "INT-001", "--findings", high) == 1
    assert _loop(intent)["stages"]["clarify"] == {"state": "open"}
    assert gate.is_closed(intent, SESSION)
    low = _findings(tmp_path, "low")
    assert _run(intent, "gate", "clarify", "--intent", "INT-001", "--findings", low) == 0
    loop = _loop(intent)
    assert loop["intent"] == "INT-001" and loop["stages"]["clarify"]["state"] == "passed"
    assert loop["stages"]["clarify"]["findings"] == 1
    assert not gate.is_closed(intent, SESSION)              # SR-196 EX-2: edits proceed
    assert _run(intent, "gate", "plan", "--intent", "INT-001", "--findings", low) == 0
    assert _loop(intent)["stages"]["plan"]["state"] == "passed"
    events = [e.payload for e in open_core(intent).events() if e.kind == "intent-gate"]
    assert [e["stage"] for e in events] == ["clarify", "plan"]
    assert events[0] == {"intent": "INT-001", "digest": DIGEST, "stage": "clarify", "findings": 1}
    assert open_core(intent).status(["SR-040"])["SR-040"].confirmation == "proposed"


@pytest.mark.sr("SR-225")
@pytest.mark.parametrize("reason", [clarify.GATE_REASON_CARD, clarify.GATE_REASON_COULDNT,
                                    clarify.GATE_REASON_CHECKING])
def test_a_passed_clarify_gate_leaves_a_hold_only_the_owner_or_the_check_opens(
        intent: Path, tmp_path: Path, reason: str) -> None:
    gate.close(intent, SESSION, DIGEST, reason)
    low = _findings(tmp_path, "low")
    assert _run(intent, "gate", "clarify", "--intent", "INT-001", "--findings", low) == 0
    assert gate.is_closed(intent, SESSION) and gate.closed_reason(intent, SESSION) == reason


def test_without_a_session_no_loop_is_claimed(intent: Path, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.stale import SESSION_ENV

    for name in SESSION_ENV:
        monkeypatch.delenv(name, raising=False)
    gate.close(intent, SESSION, DIGEST, gate.INTENT_CHANGE + " SR-040")
    argv = ["gate", "clarify", "--intent", "INT-001", "--findings", _findings(tmp_path, "low"),
            "--root", str(intent)]
    assert cmd_intent.run("intent", argv) == 1
    assert _loop(intent)["intent"] is None and gate.is_closed(intent, SESSION)


@pytest.mark.sr("SR-253")
def test_sr197_ex2_an_intent_no_requirement_derives_from_is_not_done(
        repo: Path, write_record: Any, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    write_record(repo, int_text(1))
    cmd_intent.open_loop(repo, SESSION, DIGEST)
    low = _findings(tmp_path, "low")
    _run(repo, "gate", "clarify", "--intent", "INT-001", "--findings", low)
    _run(repo, "gate", "plan", "--intent", "INT-001", "--findings", low)
    assert _run(repo, "done", "--intent", "INT-001") == 1
    assert "no requirement derives from INT-001" in capsys.readouterr().err
    assert _loop(repo)["stages"]["build"] == {"state": "open"}


@pytest.mark.sr("SR-222")
def test_sr194_ex3_done_refuses_while_the_proof_is_not_shown(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert _run(intent, "done", "--intent", "INT-001") == 1
    assert "the plan gate has not passed" in capsys.readouterr().err
    low = _findings(tmp_path, "low")
    _run(intent, "gate", "clarify", "--intent", "INT-001", "--findings", low)
    _run(intent, "gate", "plan", "--intent", "INT-001", "--findings", low)
    assert _run(intent, "done", "--intent", "INT-001") == 1
    err = capsys.readouterr().err
    assert "SR-040" in err and "no proof" in err
    assert _loop(intent)["stages"]["build"] == {"state": "open"}


@pytest.mark.sr("SR-253")
def test_sr197_ex2_a_stated_proof_not_shown_keeps_the_intent_open(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    low = _findings(tmp_path, "low")
    _run(intent, "gate", "clarify", "--intent", "INT-001", "--findings", low)
    _run(intent, "gate", "plan", "--intent", "INT-001", "--findings", low)
    proof.set_plan(open_core(intent), "SR-040", "run the command and see it", "command")
    assert _run(intent, "done", "--intent", "INT-001") == 1
    assert "SR-040" in capsys.readouterr().err
    assert _run(intent, "status") == 0
    assert capsys.readouterr().out.strip() == "INT-001: clarify passed, plan passed, build open"
    (intent / "out.txt").write_text("it worked\n", encoding="utf-8")
    proof.set_evidence(open_core(intent), "SR-040", "out.txt", "the command printed it", True)
    assert _run(intent, "done", "--intent", "INT-001") == 0
    assert not cmd_intent.loop_path(intent, SESSION, DIGEST).exists()   # SR-308: ended loop
    assert len([e for e in open_core(intent).events() if e.kind == "intent-done"]) == 1
    assert _run(intent, "status") == 0
    assert "no intent loop is open" in capsys.readouterr().out


def test_without_a_loop_verb_the_command_captures_an_intent(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.capture import cli as capture_cli

    seen: list[list[str]] = []
    monkeypatch.setattr(capture_cli, "run", lambda command, argv: seen.append(argv) or 0)
    assert cmd_intent.run("intent", ["--quote", "q", "--readback", "r"]) == 0
    assert seen == [["--quote", "q", "--readback", "r"]]
