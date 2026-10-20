"""What the band's loop pane reads (SR-305): ``plumb intent status --json`` gives each step's
gate with the low findings left, the tasks left, the records of the loop's intent by title and
each requirement's proof shown or not; nothing about agents or tokens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from understand import test_intent_loop
from understand.test_intent_loop import _findings, _run

pytestmark = pytest.mark.sr("SR-305")

intent = test_intent_loop.intent   # INT-001, SR-040 deriving from it, and an open loop


def _status(repo: Path, capsys: pytest.CaptureFixture[str]) -> dict:
    capsys.readouterr()
    assert _run(repo, "status", "--json") == 0
    [loop] = json.loads(capsys.readouterr().out)
    return loop


def test_sr305_ex1_gates_with_their_low_findings_and_the_task_left(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-305 EX-1: clarify and plan passed with 2 low findings each; build 3 of 4, one left."""
    for stage in ("clarify", "plan"):
        assert _run(intent, "gate", stage, "--intent", "INT-001",
                    "--findings", _findings(tmp_path, "low", "low")) == 0
    assert _run(intent, "progress", "--task", "building", "--done", "3", "--total", "4",
                "--left", "the pane of the loop") == 0
    loop = _status(intent, capsys)
    assert loop["step"] == "build"
    for stage in ("clarify", "plan"):
        assert loop["stages"][stage]["state"] == "passed"
        assert loop["stages"][stage]["left"] == ["a low finding", "a low finding"]
    assert (loop["tasks"]["done"], loop["tasks"]["total"], loop["tasks"]["left"]) == (
        3, 4, ["the pane of the loop"])


def test_sr305_ex2_requirements_by_title_with_proof_shown_or_not(
        intent: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-305 EX-2: the loop's records by title, and SR-040's proof not shown yet (the clarify
    gate names the loop's intent)."""
    assert _run(intent, "gate", "clarify", "--intent", "INT-001",
                "--findings", _findings(tmp_path)) == 0
    loop = _status(intent, capsys)
    assert [r["id"] for r in loop["records"]] == ["INT-001", "SR-040"]
    assert all(r["title"] for r in loop["records"])
    assert [(p["id"], p["shown"]) for p in loop["proofs"]] == [("SR-040", False)]


def test_sr305_ex3_no_agent_or_token_in_what_the_pane_reads(
        intent: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-305 EX-3: what the pane reads carries no agent names, counts or tokens."""
    text = json.dumps(_status(intent, capsys)).lower()
    assert "agent" not in text and "token" not in text
