"""SR-190: a verdict on a record whose premise is its quote alone carries the mark."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.test_judge_job import (
    _apply,
    build_job,
    intent_text,
    verdict_answer,
    world,  # noqa: F401
)

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-241")


def test_verdict_marks_a_quote_only_premise(world: Path, write_record) -> None:  # noqa: F811
    write_record(world, intent_text(2, "no prompt names this", "Something else",
                                    will=("It happens",)))
    core = open_core(world)
    job = build_job(core, ["INT-001", "INT-002"])
    applied = _apply(core, job, verdict_answer(("INT-001", "supported", 0.9),
                                               ("INT-002", "supported", 0.9)))
    verdicts = {e["payload"]["id"]: e["payload"] for e in applied.entries
                if e["kind"] == "verdict"}
    assert verdicts["INT-002"]["premise"] == "quote-only"
    assert verdicts["INT-002"]["premise_reason"].startswith("quote not verified")
    assert "premise" not in verdicts["INT-001"]
