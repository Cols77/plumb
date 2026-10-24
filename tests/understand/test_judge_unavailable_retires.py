"""A judge question the owner has since spoken past is not repeated when the judge cannot read
the new message (no judgment backend): the old question is held back, and the edit is held
too (EX-9): the couldn't-check card closes the gate instead of a "ready"."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plumb.api import open_core
from plumb.contracts import JobError, JobResult
from plumb.understand import cmd_clarify, files, gate, jobs, ledger, queue
from understand.test_judge_cascade import world  # noqa: F401
from understand.test_judge_job import SESSION, build_job, log_prompt
from understand.test_judge_questions import answer, asking


def test_a_question_older_than_the_owners_message_is_not_repeated_when_the_judge_is_down(
        world: Path, engine_standins: Any) -> None:  # noqa: F811
    engine_standins.dispatcher.script = {"judge": answer(
        ("SR-001", "supported"), questions=[asking("SR-001")])}
    core = open_core(world)
    first = build_job(core, ["SR-001"])
    queue.enqueue(core, first)
    assert cmd_clarify.wait(open_core(world), SESSION, timeout=10).state == "ask"

    digest = log_prompt(world, "On a full board print draw, the score, then a new game.",
                        at="2999-01-01T00:00:00Z")
    # the judge job queued for the new message (its own id), which failed: no backend
    newer = files.make_job(first.kind, SESSION, first.schema,
                           {**first.inputs, "answered": [digest]},
                           created="2999-01-02T00:00:00Z")
    assert newer.id != first.id
    files.write_json_atomic(jobs.job_path(world, SESSION, newer.id), files.job_to_json(newer))
    ledger.record(world, SESSION, newer.id)
    jobs.write_result(world, SESSION, JobResult(
        job=newer.id, status="error",
        error=JobError("dispatch", "judgment.backend is not set in .plumb/config.yaml")))

    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    # not repeated, and not "ready" either (EX-9): the edit is held on the couldn't-check card
    assert outcome.state == "couldnt_check"
    assert not outcome.questions
    assert "full board" not in " ".join(outcome.lines)
    assert gate.is_closed(world, SESSION)
