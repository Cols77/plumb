"""SR-248, DEC-141: the judge model approves (by: auto-model) only after a question round, when
it says the intent is clear; its confidence is logged and never compared to a bar, the owner's
switch is not needed, and an intent is approved like any record. Without a round, nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.api import open_core
from understand.fakes import as_worker
from understand.test_judge_job import (
    SESSION,
    _apply,
    build_job,
    verdict_answer,
    world,  # noqa: F401
)
from understand.test_round_approval import owner_answers

pytestmark = pytest.mark.sr("SR-248")


def owner_on(root: Path, probability: float = 0.7, confidence: str = "medium") -> None:
    """The owner's auto-approve switch, as ``iaso config auto-approve on`` logs it."""
    open_core(root).log_append("events", "config", {"by": "owner", "auto_approve": {
        "enabled": True, "backend": "jev", "min_probability": probability,
        "min_confidence": confidence}})


def judged(root: Path, *items: tuple[str, str, float], on: bool = True, round_: bool = True,
           clear: bool = True):
    """Apply the scripted judge model's answer and write what it returns, as the worker does;
    ``round_``: the owner answered a question about the records first."""
    if on:
        owner_on(root)
    if round_:
        owner_answers(root, [i for i, _, _ in items])
    core = open_core(root)
    answer = verdict_answer(*items)
    for verdict in answer["verdicts"]:
        verdict.update(by="model", judge="fake:haiku", model="haiku", clear=clear)
    applied = _apply(core, build_job(core, [i for i, _, _ in items]), answer)
    with as_worker(root, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])
    return open_core(root), applied


def approvals(core) -> list:
    return [e for e in core.events() if e.kind == "approval"]


def test_ex2_without_a_round_nothing_is_approved_and_an_intent_is_after_one(
        world: Path) -> None:  # noqa: F811
    core, _ = judged(world, ("INT-001", "supported", 0.95), round_=False)
    assert core.status(["INT-001"])["INT-001"].confirmation == "proposed"
    assert not approvals(core)
    core, _ = judged(world, ("INT-001", "supported", 0.95), on=False)
    assert core.status(["INT-001"])["INT-001"].approved_by == "auto-model"


def test_ex4_undo_revokes_it_and_counts_as_a_no(world: Path) -> None:  # noqa: F811
    from iaso.capture.calibrate import labelled_set
    from iaso.understand import tidy

    judged(world, ("SR-001", "supported", 0.8))
    assert tidy.run("undo", ["SR-001", "--root", str(world)]) == 0
    core = open_core(world)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert [(i.record, i.label) for i in labelled_set(core)
            if i.record == "SR-001" and i.source == "revoked"] == [("SR-001", "no")]


def test_ex5_the_confidence_is_never_compared_only_clear_approves(
        world: Path) -> None:  # noqa: F811
    owner_on(world, 0.9, "high")                  # 0.3 is far under the owner's old bar
    core, _ = judged(world, ("SR-001", "supported", 0.3), on=False, clear=False)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert [e.payload["verdict"] for e in core.events() if e.kind == "verdict"] == ["supported"]
    core, _ = judged(world, ("SR-001", "supported", 0.3), on=False)
    assert core.status(["SR-001"])["SR-001"].approved_by == "auto-model"


def test_ex6_without_the_owners_switch_a_round_still_approves(world: Path) -> None:  # noqa: F811
    core, _ = judged(world, ("SR-001", "supported", 0.99), on=False, round_=False)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    core, _ = judged(world, ("SR-001", "supported", 0.99), on=False)
    assert core.status(["SR-001"])["SR-001"].confirmation == "confirmed"


def test_ex7_recheck_refuses_an_approval_with_no_round_or_not_clear_on_read(
        world: Path) -> None:  # noqa: F811
    from iaso.approvals import approval_items
    from iaso.confirm import checked

    digest = owner_answers(world, ["INT-001"])    # an answer about another record
    core = open_core(world)
    base = {"records": approval_items(core, ["SR-001"]), "by": "auto-model",
            "prompt_digest": "sha256:x", "job": "judge-1"}
    forged = [{**base, "auto": {"model": "haiku", "confidence": 0.9, "clear": True}},
              {**base, "answers": [digest],
               "auto": {"model": "haiku", "confidence": 0.9, "clear": False}},
              {**base, "answers": [digest],
               "auto": {"model": "haiku", "confidence": 0.9, "clear": True}}]
    with as_worker(world, SESSION):               # a worker wrote them anyway
        for payload in forged:
            core.log_append("events", "approval", payload)
    core = open_core(world)
    whys = [w for e, w in checked(core) if e.kind == "approval"]
    assert "no answer" in whys[0] and "clear" in whys[1] and "asked about it" in whys[2]
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
