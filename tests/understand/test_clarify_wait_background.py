"""SR-378 EX-1: ``iaso clarify --wait`` on an ordinary message answers at once: the judge jobs
queued since the owner last spoke go to the detached worker, and no model call runs in the
agent's own process."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from iaso.api import open_core
from iaso.understand import cmd_clarify, jobs, queue, worker
from understand.test_judge_job import SESSION, build_job, world  # noqa: F401

pytestmark = pytest.mark.sr("SR-378")


def test_ex1_wait_answers_within_a_second_with_three_judge_jobs_queued(
        world: Path, engine_standins: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    core = open_core(world)
    for ids in (["INT-001"], ["SR-001"], ["INT-001", "SR-001"]):
        queue.enqueue(core, build_job(core, ids))

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("clarify --wait ran a job or a process itself")

    monkeypatch.setattr(worker, "run_once", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    started = time.monotonic()
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=30)
    assert time.monotonic() - started < 1
    assert outcome.state == "ready" and cmd_clarify.JUDGING in outcome.lines
    assert engine_standins.dispatcher.calls == []
    assert len([j for j in jobs.queued(world, SESSION) if j.kind == "judge"]) == 3
