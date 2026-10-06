"""CAPTURE CS4: narrow auto-approval, opt-in and off by default (R8 B, R13 Q3; sp2 8.2,
SR-041). One test per "never" case, the owner-only switch, and the validate re-check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import agent_shell_setup, event_kinds, log_prompt, run
from jev_fixtures import calibrated

from plumb.api import open_core
from plumb.capture.autoapprove import auto_approve_state, gate
from plumb.capture.confirmations import confirmation_label

pytestmark = pytest.mark.sr("SR-041")

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


def test_owner_words_restated_are_auto_approved_and_labelled(ready, capsys) -> None:
    repo, _ = ready
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT, "requirements": [REQUIREMENT]},
                   "--prompt", digest) == 0
    assert "(confirmed by JEV)" in capsys.readouterr().out
    intent, sr = [i for i in new_ids(repo, before)]
    core = open_core(repo)
    assert core.status([intent])[intent].confirmation == "confirmed"
    assert core.status([sr])[sr].confirmation == "confirmed"
    assert confirmation_label(core, intent) == "confirmed by JEV"
    approvals = [e for e in core.log_read("events", ["approval"])
                 if e.payload.get("by") == "auto-jev"]
    assert len(approvals) == 2
    auto = approvals[0].payload["auto"]
    assert auto["model_version"] == "jev-1.13.0" and auto["confidence_label"] == "high"
    assert auto["score"] >= 0.9 and approvals[0].payload["prompt_digest"] == digest
    assert approvals[1].payload["auto"]["parts"] == 2  # wording and every example (Q3)
    from plumb.validate import validate

    assert not [f for f in validate(core) if f.severity == "error"]


def test_requirement_needs_wording_and_every_example(ready) -> None:
    repo, stub = ready
    before = set(open_core(repo).index())
    doc = {"intent": INTENT, "requirements": [{**REQUIREMENT, "examples": [
        REQUIREMENT["examples"][0],
        {"given": "HALF-FAITHFUL two negatives", "when": "multiply runs",
         "then": "it returns a positive product", "quote": "multiply returns the product"}]}]}
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, doc, "--prompt", digest) == 0
    intent, sr = new_ids(repo, before)
    assert state_of(repo, intent) == "confirmed"
    assert state_of(repo, sr) == "proposed"  # one example not supported enough


def test_yaml_without_owner_event_is_off(repo: Path, write_record, monkeypatch) -> None:
    stub = calibrated(repo, write_record, monkeypatch)
    try:
        config = repo / ".plumb" / "config.yaml"
        config.write_text(config.read_text(encoding="utf-8")
                          + "auto_approve: {enabled: true}\n", encoding="utf-8")
        before = set(open_core(repo).index())
        digest = log_prompt(repo, PROMPT)
        assert capture(repo, {"intent": INTENT}, "--prompt", digest) == 0
        [intent] = new_ids(repo, before)
        assert state_of(repo, intent) == "proposed"
        from plumb.validate import validate

        codes = [f.code for f in validate(open_core(repo))]
        assert "auto-approve-mirror" in codes
    finally:
        stub.close()


def test_never_without_passing_calibration(repo: Path, write_record, monkeypatch) -> None:
    from capture_helpers import JevStub, use_jev

    stub = JevStub()
    try:
        use_jev(repo, stub, monkeypatch)
        assert run(repo, "config", "auto-approve", "on") == 1
        assert "config" not in event_kinds(repo)
    finally:
        stub.close()


def test_never_with_the_heuristic(ready) -> None:
    repo, _ = ready
    config = repo / ".plumb" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace("backend: jev\n",
                                                                 "backend: heuristic\n", 1),
                      encoding="utf-8")
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT}, "--prompt", digest) == 0
    [intent] = new_ids(repo, before)
    assert state_of(repo, intent) == "proposed"


def test_never_for_a_decision_that_matters(ready) -> None:
    repo, _ = ready
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    doc = {"intent": INTENT, "decisions": [{"question": "add multiply next to add?",
                                            "chosen": "add multiply next to add",
                                            "alternatives": ["no"], "matters": True}]}
    assert capture(repo, doc, "--prompt", digest) == 0
    ids = new_ids(repo, before)
    dec = next(i for i in ids if i.startswith("DEC-"))
    assert state_of(repo, dec) == "proposed"


def test_never_for_an_escalated_set(ready) -> None:
    repo, _ = ready
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    doc = {"intent": {**INTENT, "mode": "escalated"}, "requirements": [REQUIREMENT]}
    assert capture(repo, doc, "--prompt", digest) == 0
    assert all(state_of(repo, i) == "proposed" for i in new_ids(repo, before))


def test_never_for_a_record_confirmed_before(ready) -> None:
    repo, _ = ready
    core = open_core(repo)
    digest = log_prompt(repo, "please build feature alphaa")
    assert gate(core, ["INT-100"], prompt_digest=digest) == []  # owner-approved before


def test_never_when_jev_is_unavailable(ready) -> None:
    repo, stub = ready
    stub.close()
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT}, "--prompt", digest) == 0
    [intent] = new_ids(repo, before)
    assert state_of(repo, intent) == "proposed"


def test_never_without_a_prompt(ready) -> None:
    repo, _ = ready
    before = set(open_core(repo).index())
    assert capture(repo, {"intent": INTENT}) == 0
    [intent] = new_ids(repo, before)
    assert state_of(repo, intent) == "proposed"


def test_model_change_suspends_until_recalibrated(ready) -> None:
    repo, stub = ready
    stub.model = "jev-1.14.0"
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT}, "--prompt", digest) == 0
    [intent] = new_ids(repo, before)
    assert state_of(repo, intent) == "proposed"
    state = auto_approve_state(open_core(repo))
    assert state.suspended and state.reason == "auto-approve suspended: model changed, " \
                                               "recalibrate"


def test_revoke_returns_the_record_to_proposed(ready, monkeypatch) -> None:
    repo, _ = ready
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT}, "--prompt", digest) == 0
    [intent] = new_ids(repo, before)
    assert state_of(repo, intent) == "confirmed"
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert run(repo, "revoke", intent) == 0  # the owner's terminal
    assert state_of(repo, intent) == "proposed"


def test_config_on_off_refused_without_terminal(repo: Path, write_record, monkeypatch,
                                                capsys) -> None:
    stub = calibrated(repo, write_record, monkeypatch)
    try:
        agent_shell_setup(monkeypatch)
        assert run(repo, "config", "auto-approve", "on") == 3
        assert run(repo, "config", "auto-approve", "off") == 3
        assert "not an interactive terminal" in capsys.readouterr().err
        assert "config" not in event_kinds(repo)
        monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
        assert run(repo, "config", "auto-approve", "on") == 3
        assert run(repo, "config", "show") == 3
        assert "config" not in event_kinds(repo)
    finally:
        stub.close()


def test_validate_rechecks_auto_jev(ready) -> None:
    repo, _ = ready
    core = open_core(repo)
    digest = log_prompt(repo, PROMPT)
    core.log_append("events", "prompt", {"digest": digest})
    # an auto-jev approval written by hand: no calibration cited, a low score
    core.log_append("events", "approval", {
        "records": [{"id": "INT-101", "hash": core.index()["INT-101"].hash}],
        "by": "auto-jev", "prompt_digest": digest,
        "auto": {"score": 0.5, "confidence_label": "low", "model_version": "jev-1.13.0",
                 "calibration": "sha256:" + "0" * 64, "claim_kind": "intent-readback"}})
    from plumb.validate import validate

    errors = [f for f in validate(open_core(repo)) if f.severity == "error"]
    assert any("auto-jev" in f.message for f in errors)


def test_show_and_off(ready, monkeypatch, capsys) -> None:
    repo, _ = ready
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert run(repo, "config", "show") == 0
    assert "auto-approve: effective" in capsys.readouterr().out
    assert run(repo, "config", "auto-approve", "off") == 0
    assert not auto_approve_state(open_core(repo)).configured
    assert "enabled: false" in (repo / ".plumb" / "config.yaml").read_text(encoding="utf-8")
