"""SP8 lane JUDGE, J5: who switches settling, and when (SR-106 EX-2, EX-4, EX-8, EX-9, EX-10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.present import owner_text
from understand.test_judge_job import intent_text, log_prompt, requirement_text, verdict_answer
from understand.test_settle import calibration_passing

pytestmark = pytest.mark.sr("SR-106")

SESSION = "s1"
REQ, INT = "example-restatement", "intent-readback"


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


def configs(repo: Path, kind: str) -> list[Any]:
    return [e for e in open_core(repo).events()
            if e.kind == "settle-config" and e.payload["kind"] == kind]


def judged_once(repo: Path) -> None:
    """The judge has logged a score (what a calibration is made of)."""
    open_core(repo).log_append("events", "verdict", {
        "job": "judge-1", "id": "SR-001", "hash": "sha256:1", "verdict": "supported",
        "beyond": [], "contradicts": [], "score": 0.9, "model": "haiku",
        "premise_digest": "sha256:2"})


def owner_says(repo: Path, kind: str, on: bool) -> None:
    """The owner's switch, as their own terminal writes it (no agent marker)."""
    open_core(repo).log_append("events", "settle-config", {
        "kind": kind, "on": on, "via": "typed", "calibration": ""})


def test_ex2_intents_told_once_stays_off_until_the_owner_turns_it_on(repo: Path) -> None:
    from plumb.understand import settle

    calibration_passing(open_core(repo), kinds=(INT,))
    first = settle.refresh(open_core(repo), SESSION)
    (offer,) = [c for c in first.cards if c.kind == "settle_offer"]
    assert offer.owner_only is True and "/plumb settle on intent" in " ".join(offer.resolutions)
    assert settle.state(open_core(repo), "intent").on is False
    again = settle.refresh(open_core(repo), SESSION)
    assert [c for c in again.cards if c.kind == "settle_offer"] == []      # told once
    assert settle.state(open_core(repo), "intent").on is False             # stays off
    owner_says(repo, "intent", True)
    state = settle.state(open_core(repo), "intent")
    assert state.on is True and state.via == "typed"
    assert settle.active(open_core(repo), "intent") is True


def test_ex8_requirements_switch_on_by_themselves_told_once_logged_with_calibration(
        repo: Path) -> None:
    from plumb.understand import settle

    calibration = calibration_passing(open_core(repo), kinds=(REQ,))
    first = settle.refresh(open_core(repo), SESSION)
    state = settle.state(open_core(repo), "requirement")
    assert state.on is True and state.via == "calibration"
    assert state.calibration == calibration.digest        # logged with the calibration
    ((key, text),) = first.notices
    assert text == owner_text.SETTLE_ON_REQUIREMENTS and "/plumb settle off requirement" in text
    assert [c for c in first.cards if c.kind == "settle_offer"] == []
    assert len(configs(repo, "requirement")) == 1
    second = settle.refresh(open_core(repo), SESSION)
    assert second.notices == [] and len(configs(repo, "requirement")) == 1
    assert settle.active(open_core(repo), "requirement") is True


def test_ex9_owner_switched_off_never_switched_on_again(repo: Path) -> None:
    from plumb.understand import settle

    owner_says(repo, "requirement", False)
    calibration_passing(open_core(repo), kinds=(REQ,))
    out = settle.refresh(open_core(repo), SESSION)
    assert out.notices == []
    state = settle.state(open_core(repo), "requirement")
    assert state.on is False and state.via == "typed"
    assert [e.payload["via"] for e in configs(repo, "requirement")] == ["typed"]
    assert settle.owner_off(open_core(repo), "requirement") is True
    owner_says(repo, "requirement", True)                  # the owner can, plumb cannot
    assert settle.state(open_core(repo), "requirement").on is True


def test_a_forged_switch_counts_for_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent's own entries: an intent switched on by calibration, a requirement switched
    on citing no calibration, an owner switch written under the agent session."""
    from plumb.understand import settle

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    core = open_core(repo)
    core.log_append("events", "settle-config", {"kind": "intent", "on": True,
                                                "via": "calibration", "calibration": "x"})
    core.log_append("events", "settle-config", {"kind": "requirement", "on": True,
                                                "via": "calibration", "calibration": "nothing"})
    core.log_append("events", "settle-config", {"kind": "intent", "on": True, "via": "typed",
                                                "calibration": ""})
    core.log_append("events", "settle-config", {"kind": "intent", "on": True, "via": "typed",
                                                "calibration": "", "quote": "turn settling on",
                                                "prompt_digest": "sha256:" + "0" * 64})
    fresh = open_core(repo)
    assert settle.state(fresh, "intent").on is False
    assert settle.state(fresh, "requirement").on is False


def test_the_typed_command_in_the_entry_must_say_the_same_thing(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.approvals import prompt_digest
    from plumb.understand import settle

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    quote = "/plumb settle on requirement"
    base = {"on": True, "via": "typed", "calibration": "", "quote": quote,
            "prompt_digest": prompt_digest(quote)}
    core = open_core(repo)
    core.log_append("events", "settle-config", {**base, "kind": "intent"})   # other kind
    assert settle.state(open_core(repo), "intent").on is False
    core.log_append("events", "settle-config", {**base, "kind": "requirement"})
    assert settle.state(open_core(repo), "requirement").on is True


def test_ex10_model_change_suspends_then_requirements_return_intents_only_if_owner_had(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.capture import calibrate
    from plumb.understand import settle

    judged_once(repo)
    calibration_passing(open_core(repo), kinds=(REQ, INT))
    owner_says(repo, "intent", True)
    settle.refresh(open_core(repo), SESSION)
    core = open_core(repo)
    assert settle.active(core, "requirement") and settle.active(core, "intent")
    # a new model version
    (repo / ".plumb" / "config.yaml").write_text("understand:\n  model: sonnet\n",
                                                 encoding="utf-8")
    core = open_core(repo)
    assert settle.suspension(core, "requirement") == "the model or the prompt changed"
    assert not settle.active(core, "requirement") and not settle.active(core, "intent")
    before = len([e for e in core.events() if e.kind == "calibration"])
    settle.refresh(core, SESSION)                          # the evaluation set has not passed
    assert len([e for e in open_core(repo).events() if e.kind == "calibration"]) == before
    assert not settle.active(open_core(repo), "requirement")
    # the evaluation set passes, calibration reruns (from the logged scores)
    fingerprint = calibrate.fingerprint(open_core(repo))
    open_core(repo).log_append("events", "eval-run", {
        **fingerprint, "cases": [{"passed": True}] * 3, "passed": 3, "false_gap_rate": 0.0})
    reran: list[str] = []

    def fake_calibrate(core: Any, **_: Any):
        entry = calibration_passing(core, kinds=(REQ, INT))
        reran.append(entry.digest)
        return entry, {}

    monkeypatch.setattr(calibrate, "calibrate", fake_calibrate)
    # an owner label since the model changed makes the rerun due; the pass of the set allows it
    out = settle.refresh(open_core(repo), SESSION)
    assert out.calibrated and len(reran) == 1
    fresh = open_core(repo)
    assert settle.state(fresh, "requirement").calibration == reran[0]
    assert settle.state(fresh, "requirement").via == "calibration"
    assert settle.active(fresh, "requirement") is True
    assert settle.active(fresh, "intent") is True          # the owner had switched it on
    assert out.notices and out.notices[0][1] == owner_text.SETTLE_ON_REQUIREMENTS


def test_ex10_intents_the_owner_never_switched_on_stay_off_and_owner_off_requirements_too(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.capture import calibrate
    from plumb.understand import settle

    judged_once(repo)
    calibration_passing(open_core(repo), kinds=(REQ, INT))
    owner_says(repo, "requirement", False)
    settle.refresh(open_core(repo), SESSION)               # the owner is offered the intent switch
    (repo / ".plumb" / "config.yaml").write_text("understand:\n  model: sonnet\n",
                                                 encoding="utf-8")
    open_core(repo).log_append("events", "eval-run", {
        **calibrate.fingerprint(open_core(repo)), "cases": [{"passed": True}], "passed": 1})
    monkeypatch.setattr(calibrate, "calibrate", lambda core, **_: (
        calibration_passing(core, kinds=(REQ, INT)), {}))
    settle.refresh(open_core(repo), SESSION)
    fresh = open_core(repo)
    assert settle.state(fresh, "intent").on is False
    assert settle.state(fresh, "requirement").on is False
    assert settle.active(fresh, "intent") is False and settle.active(fresh, "requirement") is False


def test_a_calibration_that_stops_passing_leaves_every_supported_record_to_the_trial(
        repo: Path, write_record) -> None:
    from plumb.understand import judge, settle

    log_prompt(repo, "M")
    write_record(repo, intent_text(1, "m", "Intent", prompt="sha256:" + "a" * 64))
    write_record(repo, requirement_text(1, "R", "r", intent=1,
                                        examples=(("g", "w", "t"),)))
    calibration_passing(open_core(repo), kinds=(REQ,))
    settle.refresh(open_core(repo), SESSION)
    assert settle.active(open_core(repo), "requirement")
    failing = open_core(repo).log_append("events", "calibration", {
        "backend": "judge", "source": "logged",
        "per_kind": {REQ: {"passing": False, "threshold": None}},
        **__import__("plumb.capture.calibrate", fromlist=["x"]).fingerprint(open_core(repo))})
    assert failing.digest
    assert not settle.active(open_core(repo), "requirement")
    job = judge.build(open_core(repo), SESSION, records=["SR-001"])
    applied = judge.apply(open_core(repo), job, verdict_answer(("SR-001", "supported", 0.99)))
    assert [e for e in applied.entries if e["kind"] == "approval"] == []


# ---- the owner's command ---------------------------------------------------------------------


def run_cmd(repo: Path, *argv: str) -> int:
    from plumb.understand import cmd_settle

    return cmd_settle.run("settle", [*argv, "--root", str(repo)])


def test_settle_on_refused_in_prose_and_from_the_agent_shell(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """SR-106 EX-4: prose does not turn settling on; the reply names the command and the
    button. The agent's shell cannot either."""
    from plumb.understand import settle

    calibration_passing(open_core(repo), kinds=(INT,))
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    prose = log_prompt(repo, "turn settling on")
    assert run_cmd(repo, "on", "intent", "--prompt", prose) == 3
    err = capsys.readouterr().err
    assert "/plumb settle on intent" in err and "button" in err
    from understand.fakes import owner_level

    assert owner_level(err.replace("plumb: ", "")) == []
    assert settle.state(open_core(repo), "intent").on is False
    # no typed message at all: the agent's shell is not the owner's terminal
    assert run_cmd(repo, "on", "intent") == 3
    assert "Only you switch settling" in capsys.readouterr().err
    # a typed command for another kind is not this command
    other = log_prompt(repo, "/plumb settle on requirement")
    assert run_cmd(repo, "on", "intent", "--prompt", other) == 3
    assert settle.state(open_core(repo), "intent").on is False
    # a message the agent logged itself (not the prompt hook) is not the owner's
    assert run_cmd(repo, "on", "intent", "--prompt", "sha256:" + "0" * 64) == 3


def test_the_typed_command_turns_settling_on_and_off(
        repo: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from plumb.understand import settle

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent-1")
    typed = log_prompt(repo, "/plumb settle on intent")
    assert run_cmd(repo, "on", "intent", "--prompt", typed) == 0
    assert "Settling for intent is now on" in capsys.readouterr().out
    entry = configs(repo, "intent")[-1]
    assert entry.payload["via"] == "typed" and entry.payload["quote"] == "/plumb settle on intent"
    assert settle.state(open_core(repo), "intent").on is True
    off = log_prompt(repo, "/plumb settle off")
    assert run_cmd(repo, "off", "--prompt", off) == 0
    fresh = open_core(repo)
    assert not settle.state(fresh, "intent").on and not settle.state(fresh, "requirement").on
    assert settle.owner_off(fresh, "requirement") is True


def test_the_owners_own_terminal_turns_settling_on(repo: Path, capsys) -> None:
    from plumb.understand import settle

    assert run_cmd(repo, "on", "requirement") == 0          # the test process is the terminal
    assert settle.state(open_core(repo), "requirement").on is True
    assert run_cmd(repo) == 0
    assert "Settling for requirement: on" in capsys.readouterr().out
    assert run_cmd(repo, "on", "decision") == 2             # no such kind
