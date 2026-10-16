"""CAPTURE CS4: narrow auto-approval, opt-in and off by default (R8 B, R13 Q3; sp2 8.2,
SR-041). One test per "never" case, the owner-only switch, and the validate re-check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import log_prompt, run
from jev_fixtures import calibrated

from plumb.api import open_core
from plumb.capture.autoapprove import auto_approve_state

PROMPT = "add multiply next to add; multiply returns the product of two numbers"
INTENT = {"quote": "add multiply next to add", "readback": "add multiply next to add",
          "will": ["multiply next to add"]}
REQUIREMENT = {"title": "multiply returns the product",
               "statement": "multiply returns the product of two numbers",
               "examples": [{"given": "two numbers", "when": "multiply runs",
                             "then": "it returns the product",
                             "quote": "multiply returns the product of two numbers"}]}


@pytest.fixture
def ready(repo: Path, write_record, monkeypatch):
    stub = calibrated(repo, write_record, monkeypatch, requirements=True)
    assert run(repo, "config", "auto-approve", "on") == 0  # the owner's terminal (test)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")  # the agent captures
    yield repo, stub
    stub.close()


def capture(repo: Path, doc: dict, *extra: str) -> int:
    path = repo / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return run(repo, "capture", "--file", str(path), *extra)


def new_ids(repo: Path, before: set[str]) -> list[str]:
    return sorted(set(open_core(repo).index()) - before)


def state_of(repo: Path, record_id: str) -> str:
    return open_core(repo).status([record_id])[record_id].confirmation


@pytest.mark.sr("SR-039")
def test_an_equivalent_model_name_does_not_suspend(ready) -> None:
    """OpenRouter names the calibrated jev-1.13.0 typesafe/jev-1.13-20260917: same version."""
    repo, stub = ready
    stub.model = "typesafe/jev-1.13-20260917"
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT}, "--prompt", digest) == 0
    [intent] = new_ids(repo, before)
    assert state_of(repo, intent) == "confirmed"
    state = auto_approve_state(open_core(repo))
    assert not state.suspended and state.reason == "on"
    from plumb.validate import validate

    assert not [f for f in validate(open_core(repo)) if f.severity == "error"]


@pytest.mark.sr("SR-186")
def test_a_judge_model_change_after_a_logged_calibration_suspends_settling(ready) -> None:
    """SR-186 EX-4: the fingerprint's judge model differs from understand.judge_model now."""
    from plumb.capture.calibrate import fingerprint

    repo, _ = ready
    core = open_core(repo)
    assert not auto_approve_state(core).suspended
    core.log_append("events", "calibration", {
        "backend": "jev", "model_version": "jev-1.13.0", "source": "logged",
        "per_kind": {"intent-readback": {"passing": True, "threshold": 0.5}},
        **fingerprint(core), "model": "sonnet"})          # made while judge_model was sonnet
    state = auto_approve_state(core)
    assert state.suspended and state.reason.startswith("auto-approve suspended")
