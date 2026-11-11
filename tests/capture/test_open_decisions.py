"""The open decisions that matter (R1/R11, owner decision 5): a superseded DEC is closed and
never blocks the one-question-per-message queue. One test per entry point that reads the
rule: the stop hook, ``next_question`` and the escalation trigger
(``iaso.capture.clarify.open_decisions``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import record_text

from iaso.api import open_core
from iaso.capture.clarify import next_question, open_decisions
from iaso.capture.records import decide

pytestmark = pytest.mark.sr("SR-223")


@pytest.fixture
def superseded(repo: Path, write_record) -> Path:
    """DEC-001 (matters) is answered "B" by superseding it with DEC-002, which the owner
    confirms; DEC-003 (matters) is the next decision that must be asked."""
    from iaso.approvals import approve

    write_record(repo, record_text("INT-021", "calculator work", quote="add things",
                                   readback="add things"))
    write_record(repo, record_text("SR-010", "add returns the sum", statement="add sums",
                                   links=[{"kind": "derives_from", "to": "INT-021"}]))
    core = open_core(repo)
    first = decide(core, "floats too?", "A", ["B"], matters=True, decides=["SR-010"])
    assert first.id == "DEC-001"
    answer = decide(open_core(repo), "", "B", [], matters=True, supersede="DEC-001")
    assert answer.id == "DEC-002"
    approve(open_core(repo), ["DEC-002"])
    later = decide(open_core(repo), "negative numbers?", "reject", ["allow"], matters=True,
                   decides=["SR-010"])
    assert later.id == "DEC-003"
    return repo


def test_rule_skips_superseded_and_confirmed(superseded: Path) -> None:
    core = open_core(superseded)
    assert open_decisions(core.index(), core.status(), ["SR-010"]) == ["DEC-003"]


def test_next_question_skips_the_superseded_decision(superseded: Path) -> None:
    assert next_question(open_core(superseded), ["SR-010"]) == "DEC-003"


def test_escalation_does_not_count_the_superseded_decision(superseded: Path) -> None:
    from iaso.capture.escalation import escalation

    found = escalation(open_core(superseded), matched=["SR-010"])
    assert not [s for s in found if s.trigger == "decisions"]
