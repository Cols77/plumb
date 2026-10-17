"""The intent loop's step and tasks as the band draws them (SR-291): the loop file's ``step``,
``tasks`` and ``stopped``, and ``plumb intent progress``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.understand import cmd_intent, files
from understand import test_intent_loop
from understand.test_intent_loop import DIGEST, SESSION, _findings, _run

pytestmark = pytest.mark.sr("SR-291")

intent = test_intent_loop.intent   # INT-001, SR-040 deriving from it, and an open loop


def _loop(repo: Path) -> dict[str, Any]:
    return files.read_json(cmd_intent.loop_path(repo, SESSION, DIGEST))


def test_a_new_loop_is_at_clarify_with_no_task(intent: Path) -> None:
    loop = _loop(intent)
    assert (loop["step"], loop["tasks"], loop["stopped"]) == ("clarify", None, None)


def test_sr291_ex1_plan_step_with_three_of_seven_items_written(intent: Path,
                                                               tmp_path: Path) -> None:
    """SR-291 EX-1: the clarify gate passed and the plan has 7 items, 3 written."""
    assert _run(intent, "progress", "--task", "clarifying", "--done", "4", "--total", "4") == 0
    assert _run(intent, "gate", "clarify", "--intent", "INT-001",
                "--findings", _findings(tmp_path, "low")) == 0
    assert _loop(intent)["tasks"] is None    # the plan step starts with no task drawn
    assert _run(intent, "progress", "--task", "writing the plan",
                "--done", "3", "--total", "7") == 0
    loop = _loop(intent)
    assert loop["step"] == "plan"
    assert {k: loop["tasks"][k] for k in ("label", "done", "total")} == {
        "label": "writing the plan", "done": 3, "total": 7}


def test_sr291_ex2_clarify_with_two_of_four_questions_answered(intent: Path) -> None:
    """SR-291 EX-2: the loop is in clarify with 2 of 4 questions answered."""
    assert _run(intent, "progress", "--task", "clarifying", "--done", "1", "--total", "4") == 0
    started = _loop(intent)["tasks"]["started_at"]
    assert _run(intent, "progress", "--task", "clarifying", "--done", "2", "--total", "4") == 0
    loop = _loop(intent)
    assert loop["step"] == "clarify"
    assert loop["tasks"] == {"label": "clarifying", "done": 2, "total": 4, "started_at": started}


def test_sr291_ex3_build_with_an_unknown_total(intent: Path, tmp_path: Path) -> None:
    """SR-291 EX-3: the build step with an unknown total keeps no total and its start time."""
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path)) == 0
    assert _run(intent, "progress", "--task", "building") == 0
    loop = _loop(intent)
    assert loop["step"] == "build"
    assert loop["tasks"]["total"] is None and loop["tasks"]["started_at"]


def test_sr291_ex4_intent_done_closes_the_loop(intent: Path, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-291 EX-4 (data side): after intent done the loop is proven, with no task left."""
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path)) == 0
    from plumb.capture import proof
    monkeypatch.setattr(proof, "not_shown", lambda core, ids: [])
    assert _run(intent, "done", "--intent", "INT-001") == 0
    loop = _loop(intent)
    assert (loop["step"], loop["tasks"], loop["stopped"]) == ("proven", None, None)
    assert _run(intent, "progress", "--task", "late") != 0    # no open loop to draw


def test_sr291_ex6_a_refused_gate_marks_the_step_stopped(intent: Path, tmp_path: Path) -> None:
    """SR-291 EX-6: a refused gate stops the current step, naming what it waits for."""
    assert _run(intent, "gate", "clarify", "--intent", "INT-001",
                "--findings", _findings(tmp_path, "high", "medium")) != 0
    loop = _loop(intent)
    assert loop["step"] == "clarify"
    assert loop["stopped"] == "the clarify gate: 2 finding(s) to fix"
    assert _run(intent, "gate", "clarify", "--intent", "INT-001",
                "--findings", _findings(tmp_path)) == 0
    assert _loop(intent)["stopped"] is None


@pytest.mark.parametrize("gate", ["passed", "failed"])
def test_sr291_ex7_ex8_a_workflow_phase_gate_reports_through_plumb(intent: Path, tmp_path: Path,
                                                                   gate: str) -> None:
    """SR-291 EX-7: the colours slice's gate passed, slice 2 of 4, reported through plumb.
    SR-291 EX-8: a phase's gate failed: the task names the phase, and no agents of plumb's own."""
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path)) == 0
    assert _run(intent, "progress", "--task", f"colours gate {gate}",
                "--done", "2", "--total", "4") == 0
    loop = _loop(intent)
    assert loop["step"] == "build"
    assert set(loop["tasks"]) == {"label", "done", "total", "started_at"}
    assert {k: loop["tasks"][k] for k in ("label", "done", "total")} == {
        "label": f"colours gate {gate}", "done": 2, "total": 4}


def test_progress_refuses_a_bad_count(intent: Path) -> None:
    assert _run(intent, "progress", "--task", "x", "--total", "0") != 0
    assert _loop(intent)["tasks"] is None
