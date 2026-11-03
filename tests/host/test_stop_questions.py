"""SR-361 EX-5: judge questions raised while the agent worked reach it before it stops: the stop
hook blocks once per set of open questions, telling it to ask them now; the band alone reaches
nobody."""

from __future__ import annotations

from pathlib import Path

import pytest
from host.test_answer_rejudge import ASK, judge_asks, world  # noqa: F401
from host.test_stop import _block, run_stop, start_turn
from understand.test_judge_job import SESSION

from plumb.hosts.claude_code import ask_gate, stop

pytestmark = pytest.mark.sr("SR-361")

OTHER = "Should the faster pages also work offline?"


@pytest.fixture(autouse=True)
def attended(monkeypatch: pytest.MonkeyPatch) -> None:
    """The question tool is there: an attended main session."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")


def test_the_stand_in_question_tool_counts_as_the_question_tool(  # noqa: F811
        world: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    """DEC-407: a headless run with the stand-in tool (the flag set, nobody attending) is told
    to ask, once per set, exactly as an attended session is."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED")
    monkeypatch.setenv(ask_gate.STAND_IN_ENV, "1")
    judge_asks(world, (ASK, ["SR-001"]))
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION)) == \
        stop.ASK_WAITING.format(n=1, s="")
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION)) is None


def test_ex5_open_questions_block_the_stop_once_per_set(world: Path, hook_input) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    start_turn(world, SESSION)
    reason = _block(run_stop(world, hook_input, session=SESSION))
    assert reason == stop.ASK_WAITING.format(n=1, s="")
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION)) is None     # told once
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION)) == \
        stop.ASK_WAITING.format(n=2, s="s")


def test_no_block_without_questions_or_after_a_block(world: Path, hook_input) -> None:  # noqa: F811
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION)) is None
    judge_asks(world, (ASK, ["SR-001"]))
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION, active=True)) is None

