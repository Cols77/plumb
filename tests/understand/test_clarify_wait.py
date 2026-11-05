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
from plumb.understand import clarify, cmd_clarify, files, gate, hooks, worker
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
    # SR-223 EX-15: the question goes to the question tool, never a card; no edit is denied
    assert outcome.state == "ask" and outcome.digest == digest
    assert [q["question"] for q in outcome.questions] == ["Which format?"]
    assert owner_level(outcome.questions[0]["question"]) == []
    assert not gate.is_closed(repo, SESSION)
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
    assert first.state == "couldnt_check" and first.lines == [cmd_clarify.SHOW_STILL_CHECKING]
    assert gate.is_closed(repo, SESSION)                    # no build started
    release.set()
    runner.join(10)
    second = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert second.state == "ask" and second.digest == digest   # the late result is asked
    assert len(engine_standins.dispatcher.ran("clarify")) == 1


def test_runs_the_job_itself_when_none_queued(repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    core = open_core(repo)
    digest = log_prompt(repo, "/plumb clarify let users export their data", session=SESSION)
    assert not list(files.jobs_dir(repo, SESSION).glob("*.json"))
    outcome = cmd_clarify.wait(core, SESSION, timeout=5)
    assert outcome.state == "ask" and outcome.digest == digest
    assert len(engine_standins.dispatcher.ran("clarify")) == 1
    assert not gate.is_closed(repo, SESSION)   # SR-223: no question denies a tool call


def test_same_job_never_runs_twice(repo: Path, engine_standins: Any) -> None:
    engine_standins.dispatcher.script = {"clarify": CARD}
    core, _ = _say(repo)
    worker.run_once(core, SESSION)
    for _ in range(3):
        outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
        assert outcome.state == "ask"
    assert len(engine_standins.dispatcher.ran("clarify")) == 1
    assert len(list(files.jobs_dir(repo, SESSION).glob("clarify-*.json"))) == 1


def test_the_same_words_sent_again_get_their_own_check(repo: Path, engine_standins: Any) -> None:
    text = "/plumb clarify let users export their data"
    ctx = SimpleNamespace(session_id=SESSION)
    engine_standins.dispatcher.failing("run", "the model could not be reached")
    digest = log_prompt(repo, text, session=SESSION, at="2026-10-06T10:00:00Z")
    hooks.on_prompt(ctx, open_core(repo), {"digest": digest, "text": text})
    worker.run_once(open_core(repo), SESSION)
    assert cmd_clarify.wait(open_core(repo), SESSION, timeout=5).state == "couldnt_check"
    engine_standins.dispatcher.script = {"clarify": CARD}
    assert log_prompt(repo, text, session=SESSION, at="2026-10-06T10:05:00Z") == digest
    hooks.on_prompt(ctx, open_core(repo), {"digest": digest, "text": text})
    worker.run_once(open_core(repo), SESSION)
    assert cmd_clarify.wait(open_core(repo), SESSION, timeout=5).state == "ask"
    assert len(list(files.jobs_dir(repo, SESSION).glob("clarify-*.json"))) == 2


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
    assert data["state"] == "ask"
    assert [q["question"] for q in data["questions"]] == ["Which format?"]


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
    folder = repo / ".claude" / "skills" / "plumb-clarify"
    skill = (folder / "SKILL.md").read_text(encoding="utf-8")
    # SR-379: the skill points to its state table, which opens with the first action
    assert "references/clarify-states.md" in skill
    text = (folder / "references" / "clarify-states.md").read_text(encoding="utf-8")
    first = text.split("\n\n")[1]
    assert "first action" in first and "plumb clarify --wait" in first
    assert "do not build" in first.lower() and "answered" in first
    assert "{plumb}" not in text
    # what the command returns, and what to do with each outcome
    for words in ("couldn't check", "work on", "ready"):
        assert words.lower() in text.lower(), words
    assert "plumb go" not in text.replace("`/plumb go`", "")      # the agent never types it



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


def test_a_commanded_check_with_no_gap_still_hands_over_the_open_judge_questions(
        repo: Path, write_record, engine_standins: Any) -> None:
    """The ask gate counts the judge's open questions; ``--wait`` must say ``ask`` with them,
    not ``ready`` with none, or the agent never learns what to ask."""
    from understand.test_judge_job import intent_text

    from plumb.understand import judge

    write_record(repo, intent_text(1, "Pages should load faster.", "Make pages load faster"))
    engine_standins.dispatcher.script = {"clarify": NO_GAP}
    core, _ = _say(repo)
    worker.run_once(core, SESSION)
    index = open_core(repo).index()
    text = "Should every page load faster?"
    files.write_json_atomic(judge.questions_path(repo, SESSION), [
        {"key": judge.question_key(text), "job": "judge-0000000000000000",
         "records": [{"id": "INT-001", "hash": index["INT-001"].hash}], "question": text,
         "header": "Pages",
         "options": [{"label": "Yes (Recommended)", "description": "All."},
                     {"label": "No", "description": "None."}]}])
    assert not gate.is_closed(repo, SESSION)    # the check found nothing unclear
    outcome = cmd_clarify.wait(open_core(repo), SESSION, timeout=5)
    assert outcome.state == "ask"
    assert [q["question"] for q in outcome.questions] == [text]
