"""SR-191: the judge model's supported verdict confirms a requirement or decision resting on the
owner's verified words (by: auto-model); an intent or a quote-only premise waits."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.fakes import as_worker
from understand.test_judge_job import (
    SESSION,
    _apply,
    build_job,
    decision_text,
    intent_text,
    verdict_answer,
    world,  # noqa: F401
)

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-191")


def judged(root: Path, *items: tuple[str, str, float]):
    """Apply the scripted judge model's answer and write what it returns, as the worker does."""
    core = open_core(root)
    answer = verdict_answer(*items)
    for verdict in answer["verdicts"]:
        verdict.update(by="model", judge="fake:haiku", model="haiku")
    applied = _apply(core, build_job(core, [i for i, _, _ in items]), answer)
    with as_worker(root, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])
    return open_core(root), applied


def test_ex1_a_supported_requirement_is_confirmed_by_the_model_and_listed(world: Path) -> None:  # noqa: F811
    from plumb.understand.summary import Told, _confirmations

    core, applied = judged(world, ("SR-001", "supported", 0.8))
    state = core.status(["SR-001"])["SR-001"]
    assert (state.confirmation, state.approved_by) == ("confirmed", "auto-model")
    (entry,) = [e for e in core.events() if e.kind == "approval"]
    assert entry.payload["auto"] == {"model": "haiku", "confidence": 0.8}
    assert applied.cards == ()                   # nothing left to ask the owner
    told = Told(core.root, SESSION, "2000-01-01T00:00:00Z")
    (line,) = _confirmations(core, None, told)
    assert "haiku" in line and "undo SR-001" in line
    assert _confirmations(core, None, told) == ()   # said once


def test_ex2_an_intent_is_never_confirmed_by_a_model_verdict(world: Path) -> None:  # noqa: F811
    core, _ = judged(world, ("INT-001", "supported", 0.95))
    assert core.status(["INT-001"])["INT-001"].confirmation == "proposed"
    assert not [e for e in core.events() if e.kind == "approval"]


def test_ex3_a_quote_only_decision_stays_proposed(world: Path, write_record) -> None:  # noqa: F811
    write_record(world, intent_text(2, "no prompt names this", "Something else"))
    write_record(world, decision_text(1, "Which cache?", "none", intent=2))
    core, _ = judged(world, ("DEC-001", "supported", 0.9))
    assert core.status(["DEC-001"])["DEC-001"].confirmation == "proposed"
    (verdict,) = [e.payload for e in core.events() if e.kind == "verdict"]
    assert verdict["premise"] == "quote-only"


def test_ex4_undo_revokes_it_and_counts_as_a_no(world: Path) -> None:  # noqa: F811
    from plumb.capture.calibrate import labelled_set
    from plumb.understand import tidy

    judged(world, ("SR-001", "supported", 0.8))
    assert tidy.run("undo", ["SR-001", "--root", str(world)]) == 0
    core = open_core(world)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert [(i.record, i.label) for i in labelled_set(core)
            if i.record == "SR-001" and i.source == "revoked"] == [("SR-001", "no")]
