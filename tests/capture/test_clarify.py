"""CAPTURE CS1: plumb clarify gives the skill its depth and the questions that matter
(R11; sp2 9.2, SR-043)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import record_text, run

from plumb.api import open_core
from plumb.capture.clarify import clarify, next_question

pytestmark = pytest.mark.sr("SR-043")

EX = [{"id": "EX-1", "given": "an approved requirement", "when": "its statement is edited",
       "then": "the requirement is an unconfirmed edit"}]


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    from plumb.approvals import approve

    write_record(repo, record_text("SR-004", "Approvals pin exact content",
                                   statement="An approval pins the record hash", examples=EX))
    approve(open_core(repo), ["SR-004"])
    return repo


def test_maps_to_confirmed_record_is_trivial(project: Path) -> None:
    view = clarify(open_core(project), "rerun the SR-004 approval checks",
                   [{"question": "Which color?", "options": ["red", "blue"]}])
    assert view.depth == "trivial"
    assert view.questions == ()
    assert view.answered and view.answered[0].startswith("SR-004 (confirmed)")


def test_new_intent_is_incremental(project: Path) -> None:
    view = clarify(open_core(project), "let users export their data")
    assert view.depth == "incremental"
    assert "no record covers it yet" in view.reason


def test_trigger_makes_it_escalated(project: Path) -> None:
    view = clarify(open_core(project), "delete every record of former users")
    assert view.depth == "escalated" and view.escalation[0].trigger == "irreversible"


def test_cli_writes_session_depth(project: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "sess-9")
    questions = project / "q.json"
    questions.write_text(json.dumps([{"question": "Include invoices?",
                                      "options": [{"label": "yes", "will": ["invoices"]},
                                                  {"label": "no", "wont": ["invoices"]}],
                                      "recommended": "no"}]), encoding="utf-8")
    assert run(project, "clarify", "let users export their data", "--questions",
               str(questions)) == 0
    out = capsys.readouterr().out
    assert out.startswith("depth: incremental")
    assert "1. Include invoices? [yes / no] (recommended: no)" in out
    saved = json.loads((project / ".plumb" / "session" / "sess-9" / "clarify.json")
                       .read_text(encoding="utf-8"))
    assert saved["depth"] == "incremental"


def test_next_question_is_the_earliest_open_decision(project: Path, write_record) -> None:
    for n in (10, 9):
        write_record(project, record_text(f"DEC-0{n:02d}", f"q{n}", question=f"q{n}?",
                                          chosen="a", alternatives=["b"], matters=True,
                                          links=[{"kind": "decides", "to": "SR-004"}]))
    core = open_core(project)
    assert next_question(core, ["SR-004"]) == "DEC-009"
    assert next_question(core, ["SR-999"]) is None
