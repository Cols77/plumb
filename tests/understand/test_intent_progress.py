"""The intent loop's step and tasks as the band draws them (SR-291): the loop file's ``step``,
``tasks`` and ``stopped``, and ``iaso intent progress``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iaso.understand import cmd_intent, files
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
    assert loop["tasks"] == {"label": "clarifying", "done": 2, "total": 4, "started_at": started,
                             "left": []}


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
    from iaso.capture import proof
    monkeypatch.setattr(proof, "not_shown", lambda core, ids: [])
    assert _run(intent, "done", "--intent", "INT-001") == 0
    assert _loop(intent) is None      # SR-308: the ended loop's state file is removed
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
def test_sr291_ex7_ex8_a_workflow_phase_gate_reports_through_iaso(intent: Path, tmp_path: Path,
                                                                   gate: str) -> None:
    """SR-291 EX-7: the colours slice's gate passed, slice 2 of 4, reported through iaso.
    SR-291 EX-8: a phase's gate failed: the task names the phase, and no agents of iaso's own."""
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path)) == 0
    assert _run(intent, "progress", "--task", f"colours gate {gate}",
                "--done", "2", "--total", "4") == 0
    loop = _loop(intent)
    assert loop["step"] == "build"
    assert set(loop["tasks"]) == {"label", "done", "total", "started_at", "left"}
    assert {k: loop["tasks"][k] for k in ("label", "done", "total")} == {
        "label": f"colours gate {gate}", "done": 2, "total": 4}


def _build_with_a_phase_gate_line(intent: Path, tmp_path: Path) -> None:
    """Both gates passed; a workflow phase then reported 'plan gate passed' 1/4 (DEC-157)."""
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path)) == 0
    assert _run(intent, "progress", "--task", "plan gate passed",
                "--done", "1", "--total", "4") == 0
    assert _loop(intent)["tasks"]["label"] == "plan gate passed"


def test_report_d7f2612b_evidence_recorded_redraws_the_stale_phase_gate_line(
        intent: Path, tmp_path: Path) -> None:
    """report-d7f2612b: the band kept 'plan gate passed 1/4' long after the build was proven.
    Evidence recorded for the intent's requirement redraws the build task from the loop's real
    state: the proofs shown over those required, none left."""
    from iaso.api import open_core
    from iaso.capture import proof

    _build_with_a_phase_gate_line(intent, tmp_path)
    core = open_core(intent)
    proof.set_plan(core, "SR-040", "the tests of SR-040 pass", "other")
    proof.set_evidence(core, "SR-040", "https://example.test/run/1", "tests passed", True)
    loop = _loop(intent)
    assert loop["step"] == "build"
    assert {k: loop["tasks"][k] for k in ("label", "done", "total", "left")} == {
        "label": cmd_intent.PROOFS_TASK, "done": 1, "total": 1, "left": []}
    assert loop["tasks"]["started_at"]


def test_report_d7f2612b_a_refused_intent_done_redraws_the_task_from_the_proofs(
        intent: Path, tmp_path: Path) -> None:
    """report-d7f2612b: a refused `intent done` used to keep the stale words beside the stop;
    the task is the real state: 0 of 1 proofs shown, the requirement not shown named."""
    _build_with_a_phase_gate_line(intent, tmp_path)
    assert _run(intent, "done", "--intent", "INT-001") != 0
    loop = _loop(intent)
    assert loop["stopped"] == "proof shown"
    assert {k: loop["tasks"][k] for k in ("label", "done", "total", "left")} == {
        "label": cmd_intent.PROOFS_TASK, "done": 0, "total": 1,
        "left": ["SR-040 (Requirement 40): proof no proof"]}


def test_report_d7f2612b_evidence_outside_the_build_step_leaves_the_task_alone(
        intent: Path, tmp_path: Path) -> None:
    """The plan step's task stays its own words: proofs are the build's state."""
    from iaso.api import open_core
    from iaso.capture import proof

    assert _run(intent, "gate", "clarify", "--intent", "INT-001",
                "--findings", _findings(tmp_path)) == 0
    assert _run(intent, "progress", "--task", "writing the plan",
                "--done", "3", "--total", "7") == 0
    core = open_core(intent)
    proof.set_plan(core, "SR-040", "the tests of SR-040 pass", "other")
    proof.set_evidence(core, "SR-040", "https://example.test/run/1", "tests passed", True)
    loop = _loop(intent)
    assert loop["step"] == "plan" and loop["tasks"]["label"] == "writing the plan"


def test_progress_refuses_a_bad_count(intent: Path) -> None:
    assert _run(intent, "progress", "--task", "x", "--total", "0") != 0
    assert _loop(intent)["tasks"] is None


def test_sr291_ex7_a_workflow_agent_under_another_session_moves_the_owning_loop(
        intent: Path) -> None:
    """SR-291 EX-7: a workflow's subagent runs `intent progress` under its own session id; the
    open loop of the owning session takes it, so the main session's band moves."""
    argv = ["progress", "--task", "colours gate passed", "--done", "2", "--total", "4",
            "--root", str(intent), "--session", "subagent-1"]
    assert cmd_intent.run("intent", argv) == 0
    assert _loop(intent)["tasks"]["label"] == "colours gate passed"
    cmd_intent.open_loop(intent, "other", "sha256:" + "b" * 64)   # a second session's loop
    assert cmd_intent.run("intent", argv) != 0                    # whose is ambiguous


def test_sr291_a_new_loop_and_intent_done_reset_the_band_head(intent: Path, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch
                                                              ) -> None:
    """SR-291: the band's head summary and progress from a previous loop do not carry over."""
    import json

    sdir = files.session_dir(intent, SESSION)
    status = intent / ".iaso" / "session" / "status.json"

    def stale() -> None:
        (sdir / "intent.json").write_text(json.dumps({"id": "INT-001"}), encoding="utf-8")
        files.progress_path(intent, SESSION).write_text(
            json.dumps({"state": "running", "step": "reading the agent's questions to you"}),
            encoding="utf-8")
        status.write_text(json.dumps({"state": "aligned", "intent_summary": "old intent"}),
                          encoding="utf-8")

    def clean() -> None:
        assert not (sdir / "intent.json").exists()
        assert not files.progress_path(intent, SESSION).exists()
        assert files.read_json(status) == {"state": "aligned", "intent_summary": ""}

    stale()
    cmd_intent.open_loop(intent, SESSION, "sha256:" + "c" * 64)
    clean()
    stale()
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path)) == 0
    from iaso.capture import proof
    monkeypatch.setattr(proof, "not_shown", lambda core, ids: [])
    assert _run(intent, "done", "--intent", "INT-001") == 0
    clean()
