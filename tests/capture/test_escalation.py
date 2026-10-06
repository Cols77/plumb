"""CAPTURE C4: escalation suggested on the concept's triggers, once (sp2 6.1, SR-036)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import agent_shell_setup, event_kinds, log_prompt, record_text, run

from plumb.api import open_core
from plumb.capture.escalation import escalation
from plumb.contracts import DiffStats

pytestmark = pytest.mark.sr("SR-036")

EX = [{"id": "EX-1", "given": "a = 1 and b = 2", "when": "add runs", "then": "it returns 3"}]


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, record_text("INT-021", "calculator work", quote="add things",
                                   readback="add things"))
    for n in (1, 3):
        write_record(repo, record_text(f"FEAT-00{n}", f"feature {n}"))
    write_record(repo, record_text("SR-001", "add returns the sum", feature="FEAT-001",
                                   statement="add(a, b) returns the sum", examples=EX))
    write_record(repo, record_text("SR-003", "orders export as CSV", feature="FEAT-003",
                                   statement="the export writes CSV"))
    return repo


def triggers(found) -> list[str]:
    return [f.trigger for f in found]


def test_two_features_trigger_size(project: Path) -> None:
    found = escalation(open_core(project), matched=["SR-001", "SR-003"])
    assert triggers(found) == ["size"]
    assert found[0].reason == "touches 2 features (FEAT-001, FEAT-003)"
    assert found[0].line == ("plumb: consider an up-front spec: touches 2 features "
                             "(FEAT-001, FEAT-003); the owner decides")


def test_more_than_three_requirements_trigger_size(project: Path) -> None:
    found = escalation(open_core(project), matched=["SR-001"],
                       planned_requirements=["SR-new1", "SR-new2", "SR-new3"])
    assert triggers(found) == ["size"] and "changes 4 requirements" in found[0].reason


def test_contradiction_of_confirmed_triggers(project: Path) -> None:
    from plumb.approvals import approve

    approve(open_core(project), ["SR-001"])
    found = escalation(open_core(project), prompt="make add subtract", matched=["SR-001"])
    assert "contradiction" in triggers(found)
    assert "contradicts confirmed SR-001" in [f.reason for f in found]


def test_shared_surface_triggers(project: Path) -> None:
    found = escalation(open_core(project),
                       diff=DiffStats(lines=10, files=1, paths=("src/plumb/cli.py",)))
    assert triggers(found) == ["shared"]
    found = escalation(open_core(project),
                       diff=DiffStats(lines=1, files=1, paths=("tests/conftest.py",)))
    assert triggers(found) == ["shared"]


def test_hard_to_undo_triggers(project: Path) -> None:
    found = escalation(open_core(project), prompt="delete the records of former users")
    assert triggers(found) == ["irreversible"] and "delete" in found[0].reason
    assert escalation(open_core(project), prompt="tidy the docstrings") == []


def test_two_open_decisions_that_matter_trigger(project: Path, write_record) -> None:
    for n in (1, 2):
        write_record(project, record_text(f"DEC-00{n}", f"q{n}", question=f"q{n}?",
                                          chosen="a", alternatives=["b"], matters=True,
                                          links=[{"kind": "derives_from", "to": "INT-021"}]))
    found = escalation(open_core(project), matched=["INT-021"])
    assert triggers(found) == ["decisions"]
    assert "2 decisions that matter are unconfirmed" in found[0].reason


def test_large_diff_triggers(project: Path) -> None:
    found = escalation(open_core(project), diff=DiffStats(lines=450, files=3))
    assert triggers(found) == ["diff"] and "450 changed lines" in found[0].reason
    found = escalation(open_core(project), diff=DiffStats(lines=40, files=11))
    assert triggers(found) == ["diff"]


def test_declined_not_repeated(project: Path, capsys) -> None:
    diff = DiffStats(lines=450, files=3)
    assert escalation(open_core(project), diff=diff, intent="INT-021")
    assert run(project, "escalate", "decline", "--intent", "INT-021") == 0  # owner terminal
    assert escalation(open_core(project), diff=diff, intent="INT-021") == []
    assert "escalation-declined" in event_kinds(project)
    # relayed form: the owner's own words, verbatim
    digest = log_prompt(project, "no, no up-front spec for this, just do it")
    assert run(project, "escalate", "decline", "--intent", "INT-021", "--prompt", digest,
               "--quote", "no up-front spec for this") == 0
    events = list(open_core(project).log_read("events", ["escalation-declined"]))
    assert events[-1].payload["by"] == "agent-relayed"
    assert run(project, "escalate", "decline", "--intent", "INT-021", "--prompt", digest,
               "--quote", "no spec") == 3


def test_owner_decline_refused_without_terminal(project: Path, monkeypatch, capsys) -> None:
    agent_shell_setup(monkeypatch)
    assert run(project, "escalate", "decline", "--intent", "INT-021") == 3
    assert "not an interactive terminal" in capsys.readouterr().err
    assert "escalation-declined" not in event_kinds(project)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "s1")
    assert run(project, "escalate", "decline", "--intent", "INT-021") == 3
    assert "escalation-declined" not in event_kinds(project)


def test_check_command_prints_one_line(project: Path, capsys) -> None:
    assert run(project, "escalate", "check", "--matched", "SR-001", "--matched", "SR-003") == 0
    assert capsys.readouterr().out.strip() == (
        "plumb: consider an up-front spec: touches 2 features (FEAT-001, FEAT-003); "
        "the owner decides")
