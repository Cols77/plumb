"""The owner's typed commands (settle, undo, go) are used once, for the turn they were typed
in: the agent cannot replay an old typed message to undo what the owner has done since
(SR-105 EX-6, SR-106 EX-4, SR-103 EX-10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt as log_hook_prompt

from plumb.api import open_core
from plumb.understand import cmd_go, cmd_settle, gate, settle
from understand.test_judge_job import log_prompt
from understand.test_settle import SESSION
from understand.test_settle_switch import configs

pytestmark = pytest.mark.sr("SR-106")


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


def run_cmd(repo: Path, *argv: str) -> int:
    return cmd_settle.run("settle", [*argv, "--root", str(repo)])


def as_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")


def as_owner_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)


def test_a_typed_on_replayed_after_the_owner_switched_off_does_nothing(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    as_agent(monkeypatch)
    typed = log_prompt(repo, "/plumb settle on intent")
    assert run_cmd(repo, "on", "intent", "--prompt", typed) == 0
    assert settle.state(open_core(repo), "intent").on is True
    as_owner_terminal(monkeypatch)
    assert run_cmd(repo, "off", "intent") == 0                      # their terminal, or a button
    assert settle.state(open_core(repo), "intent").on is False
    as_agent(monkeypatch)
    assert run_cmd(repo, "on", "intent", "--prompt", typed) == 3     # the replay
    fresh = open_core(repo)
    assert settle.state(fresh, "intent").on is False
    assert settle.owner_latest(fresh, "intent") is False
    assert len(configs(repo, "intent")) == 2


def test_a_typed_on_the_agent_never_ran_cannot_override_a_later_switch_off(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    as_agent(monkeypatch)
    typed = log_prompt(repo, "/plumb settle on intent")
    as_owner_terminal(monkeypatch)
    open_core(repo).log_append("events", "settle-config", {      # a button, after that message
        "kind": "intent", "on": False, "via": "button", "calibration": ""})
    as_agent(monkeypatch)
    assert run_cmd(repo, "on", "intent", "--prompt", typed) == 3
    assert settle.owner_latest(open_core(repo), "intent") is False


def test_the_same_typed_words_sent_again_are_a_new_command(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    as_agent(monkeypatch)
    first = log_prompt(repo, "/plumb settle on intent")
    assert run_cmd(repo, "on", "intent", "--prompt", first) == 0
    as_owner_terminal(monkeypatch)
    assert run_cmd(repo, "off", "intent") == 0
    as_agent(monkeypatch)
    again = log_prompt(repo, "/plumb settle on intent",             # the owner typed it again
                       at="2099-01-01T00:00:00Z")
    assert again == first
    assert run_cmd(repo, "on", "intent", "--prompt", again) == 0
    assert settle.state(open_core(repo), "intent").on is True


def test_a_typed_message_that_is_not_the_current_turn_is_refused_to_the_agent(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    as_agent(monkeypatch)
    typed = log_prompt(repo, "/plumb settle on intent")
    log_prompt(repo, "now please add a readme")                      # the owner moved on
    assert run_cmd(repo, "on", "intent", "--prompt", typed) == 3
    assert settle.state(open_core(repo), "intent").on is False


def test_a_typed_undo_is_used_once(repo: Path, write_record,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from understand.test_recheck_settled import settled_world

    settled_world(repo, write_record)
    as_agent(monkeypatch)
    typed = log_prompt(repo, "/plumb undo SR-001")
    assert cmd_settle.run("undo", ["SR-001", "--prompt", typed, "--root", str(repo)]) == 0
    from understand.test_judge_job import approve

    as_owner_terminal(monkeypatch)
    approve(open_core(repo), "SR-001")                               # the owner confirmed it again
    as_agent(monkeypatch)
    assert open_core(repo).status(["SR-001"])["SR-001"].confirmation == "confirmed"
    assert cmd_settle.run("undo", ["SR-001", "--prompt", typed, "--root", str(repo)]) == 3
    assert open_core(repo).status(["SR-001"])["SR-001"].confirmation == "confirmed"
    assert len([e for e in open_core(repo).events() if e.kind == "revocation"]) == 1


pytestmark_go = pytest.mark.sr("SR-103")


@pytestmark_go
def test_an_old_typed_go_does_not_release_a_later_failed_check(
        repo: Path, engine_standins: Any) -> None:
    from understand.test_clarify_release import _failed_check

    _failed_check(repo, engine_standins, text="let users export their data")
    old_go = log_hook_prompt(repo, "/plumb go", session=SESSION)
    assert cmd_go.run("go", ["--prompt", old_go, "--root", str(repo)]) == 0
    assert not gate.is_closed(repo, SESSION)
    _failed_check(repo, engine_standins, text="let users delete their data")   # a new failure
    assert gate.is_closed(repo, SESSION)
    assert cmd_go.run("go", ["--prompt", old_go, "--root", str(repo)]) == 3     # the replay
    assert gate.is_closed(repo, SESSION)
    again = log_hook_prompt(repo, "/plumb go", session=SESSION)                 # typed again
    assert cmd_go.run("go", ["--prompt", again, "--root", str(repo)]) == 0
    assert not gate.is_closed(repo, SESSION)
