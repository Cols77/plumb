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



def test_dec435_the_prompt_hook_has_no_waiting_reminder_the_stop_hook_still_nudges(  # noqa: F811
        world: Path, hook_input) -> None:
    """DEC-435: a waiting question is not repeated at each owner message; the one nudge is at
    the end of the turn."""
    import io

    from host.fakes import FakeBackend, FakeVerify

    from plumb.hosts.claude_code import prompt

    judge_asks(world, (ASK, ["SR-001"]))
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt="carry on please", session_id=SESSION)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=world, verify=FakeVerify(),
                       backend=FakeBackend()) == 0
    assert "judge question" not in out.getvalue() and "wait for the owner" not in out.getvalue()
    start_turn(world, SESSION)
    assert _block(run_stop(world, hook_input, session=SESSION)) == \
        stop.ASK_WAITING.format(n=1, s="")


@pytest.mark.sr("SR-216")
def test_ex9_an_answer_after_the_requirement_was_superseded_binds_to_its_replacement(  # noqa: F811
        world: Path, hook_input, write_record) -> None:
    """SR-216 EX-9: the question's requirement is superseded while the owner answers; the
    answer is logged against the replacing requirement and the old question is not asked again."""
    from host.test_answer_rejudge import answer, logged
    from understand.test_judge_job import requirement_text

    from plumb.api import open_core
    from plumb.understand import judge

    judge_asks(world, (ASK, ["SR-001"]))
    write_record(world, requirement_text(2, "Pages", "Pages load in half a second",
                                         links=[{"kind": "supersedes", "to": "SR-001"}]))
    answer(world, hook_input, ASK, "Public pages (Recommended)")
    (entry,) = logged(world)
    assert [r["id"] for r in entry["asked"]["records"]] == ["SR-002"]
    assert judge.unanswered(open_core(world), SESSION) == []
