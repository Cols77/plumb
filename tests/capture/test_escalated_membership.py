"""R8 B "NEVER for an escalated spec set": a record that derives from (or decides) an escalated
INT belongs to its set even when the anchor's ``members`` does not list it
(``plumb.capture.spec.escalated_sets``). One test per entry point that reads the rule: the
auto-approval gate, the validate re-check, triage and the set state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text, run
from jev_fixtures import calibrated

from plumb.api import open_core
from plumb.capture.spec import set_state

pytestmark = [pytest.mark.sr("SR-041"), pytest.mark.sr("SR-037")]

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
    yield repo
    stub.close()


def capture(repo: Path, doc: dict, *extra: str) -> int:
    path = repo / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return run(repo, "capture", "--file", str(path), *extra)


def new_ids(repo: Path, before: set[str]) -> list[str]:
    return sorted(set(open_core(repo).index()) - before)


def state_of(repo: Path, record_id: str) -> str:
    return open_core(repo).status([record_id])[record_id].confirmation


def test_gate_never_approves_a_record_captured_against_an_escalated_intent(ready,
                                                                           capsys) -> None:
    repo = ready
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": {**INTENT, "mode": "escalated"}}, "--prompt", digest) == 0
    [anchor] = new_ids(repo, before)
    before = set(open_core(repo).index())
    capsys.readouterr()
    assert capture(repo, {"intent": anchor, "requirements": [REQUIREMENT]},
                   "--prompt", digest) == 0
    [sr] = new_ids(repo, before)
    assert state_of(repo, sr) == "proposed"
    assert f"{sr} joined its set" in capsys.readouterr().out
    approvals = open_core(repo).log_read("events", ["approval"])
    assert not [e for e in approvals if e.payload.get("by") == "auto-jev"]


def test_validate_rejects_auto_jev_of_a_record_of_an_escalated_set(ready) -> None:
    repo = ready
    before = set(open_core(repo).index())
    digest = log_prompt(repo, PROMPT)
    assert capture(repo, {"intent": INTENT, "requirements": [REQUIREMENT]},
                   "--prompt", digest) == 0
    intent, sr = new_ids(repo, before)
    assert state_of(repo, sr) == "confirmed"  # auto-jev while the intent was incremental
    path = repo / ".plumb" / "intents" / f"{intent}.md"
    path.write_text(path.read_text(encoding="utf-8").replace("mode: incremental",
                                                             "mode: escalated"),
                    encoding="utf-8")
    from plumb.validate import validate

    core = open_core(repo)
    errors = [f for f in validate(core) if f.severity == "error" and f.subject == sr]
    assert any("escalated spec set" in f.message for f in errors)
    assert core.status([sr])[sr].confirmation == "proposed"


def test_triage_never_groups_a_record_of_an_escalated_set(repo: Path, write_record) -> None:
    from plumb.capture.triage import triage

    write_record(repo, record_text("INT-020", "a set", quote="add multiply next to add",
                                   readback="add multiply next to add", mode="escalated"))
    write_record(repo, record_text("INT-022", "multiply", quote="add multiply next to add",
                                   readback="add multiply next to add",
                                   links=[{"kind": "derives_from", "to": "INT-020"}]))
    view = triage(open_core(repo))
    assert "INT-022" not in [i.id for i in view.low_risk]
    why = {i.id: i.excluded for i in view.individual}
    assert why["INT-022"] == "a member of the escalated spec INT-020"


def test_set_state_covers_records_derived_from_the_set(repo: Path, write_record) -> None:
    write_record(repo, record_text("INT-021", "export redesign", quote="redo the export",
                                   readback="Redo the export", mode="escalated",
                                   members=["SR-070"]))
    write_record(repo, record_text("SR-070", "export rule 70", statement="rule 70",
                                   links=[{"kind": "derives_from", "to": "INT-021"}]))
    assert run(repo, "spec", "approve", "INT-021") == 0  # the owner's terminal (test)
    assert set_state(open_core(repo), "INT-021") == "approved"
    assert run(repo, "new", "requirement", "--title", "export rule 71", "--statement",
               "rule 71", "--derives-from", "INT-021") == 0
    core = open_core(repo)
    added = sorted(set(core.index()) - {"INT-021", "SR-070"})
    [sr] = [i for i in added if i.startswith("SR-")]
    assert set_state(core, "INT-021") == "unconfirmed"
    assert run(repo, "spec", "approve", "INT-021") == 0
    core = open_core(repo)
    assert core.status([sr])[sr].confirmation == "confirmed"
    assert set_state(core, "INT-021") == "approved"
