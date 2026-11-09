"""SR-387: the worker sends the independent model calls of a queue out together, up to
``understand.parallel_calls``, and applies the answers one at a time in the queue's order."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from iaso.api import Core
from iaso.contracts import Applied, DispatchError
from iaso.understand import dispatch, files, jobs, queue, worker
from understand.fakes import FakeDispatcher, FakeKind, fake_kinds

pytestmark = pytest.mark.sr("SR-387")


class Recording(FakeDispatcher):
    """Sleeps a little in run() and records how many calls are out at once."""

    def __init__(self) -> None:
        super().__init__()
        self.lock = threading.Lock()
        self.out = 0
        self.peak = 0
        self.log: list[tuple[str, str]] = []       # (event, job id)
        self.failing_jobs: set[str] = set()

    def run(self, job, *, system, user, schema, on_step):
        with self.lock:
            self.out += 1
            self.peak = max(self.peak, self.out)
            self.log.append(("start", job.id))
        try:
            time.sleep(0.15)
            if job.id in self.failing_jobs:
                raise DispatchError("run", "the model could not be reached")
            return {"ok": True}
        finally:
            with self.lock:
                self.out -= 1
                self.log.append(("end", job.id))


def _setup(repo: Path, monkeypatch: pytest.MonkeyPatch, limit: int, **kind: Any):
    (repo / ".iaso" / "config.yaml").write_text(
        f"understand:\n  parallel_calls: {limit}\n", encoding="utf-8")
    dispatcher = Recording()
    monkeypatch.setattr(dispatch, "configured", lambda core: dispatcher)
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    applied: list[str] = []
    fake_kinds(monkeypatch, {"a": FakeKind("a", apply=lambda core, job, answer: (
        applied.append(job.id) or Applied(job=job.id)), **kind)})
    return Core(repo), dispatcher, applied


def _job(n: int, needs: str | None = None):
    return jobs.new_job("a", "s1", "a.v1", {"n": n}, needs=needs,
                        created=f"2026-01-01T00:00:{n:02d}Z")


def _enqueue(core: Core, count: int) -> list[Any]:
    made = [_job(n) for n in range(1, count + 1)]
    for job in reversed(made):
        queue.enqueue(core, job)
    return made


def test_parallel_calls_default_is_three_and_below_one_is_refused() -> None:
    from iaso.config import UnderstandConfig

    assert UnderstandConfig().parallel_calls == 3      # DEC-427: the owner, from the wall times
    for bad in (0, -2):
        with pytest.raises(ValueError):
            UnderstandConfig(parallel_calls=bad)


def test_ex1_six_independent_jobs_limit_three(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core, dispatcher, applied = _setup(repo, monkeypatch, 3)
    made = _enqueue(core, 6)
    assert worker.run_once(core, "s1") == [j.id for j in made]
    assert 1 < dispatcher.peak <= 3
    assert applied == [j.id for j in made]
    assert all(jobs.result(repo, "s1", j.id).status == "ok" for j in made)


def test_ex2_a_job_with_needs_is_sent_after_its_need_ended_ok(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core, dispatcher, applied = _setup(repo, monkeypatch, 3)
    first = _job(1)
    dependent = _job(2, needs=first.id)
    other = _job(3)
    for job in (other, dependent, first):
        queue.enqueue(core, job)
    worker.run_once(core, "s1")
    assert dispatcher.peak > 1                    # the independent ones did go together
    assert dispatcher.log.index(("end", first.id)) < dispatcher.log.index(("start", dependent.id))
    assert applied.index(first.id) < applied.index(dependent.id)
    assert sorted(applied) == sorted([first.id, dependent.id, other.id])


def test_ex3_one_call_fails_the_others_are_applied(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core, dispatcher, applied = _setup(repo, monkeypatch, 3)
    made = _enqueue(core, 3)
    dispatcher.failing_jobs = {made[2].id}
    worker.run_once(core, "s1")
    assert dispatcher.peak > 1
    assert applied == [made[0].id, made[1].id]
    (lost,) = queue.failures(core, "s1")
    assert lost.job == made[2].id and lost.error.step == "run"
    assert files.read_json(files.failures_path(repo, "s1"))["consecutive"] == 1
    dispatcher.failing_jobs = set()
    assert queue.retry_failed(core, "s1") == [made[2].id]
    worker.run_once(core, "s1")
    assert applied[-1] == made[2].id and queue.failures(core, "s1") == []


def test_ex4_limit_one_runs_one_after_another(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core, dispatcher, applied = _setup(repo, monkeypatch, 1)
    made = _enqueue(core, 4)
    assert worker.run_once(core, "s1") == [j.id for j in made]
    assert dispatcher.peak == 1
    assert applied == [j.id for j in made]
    assert [e for e, _ in dispatcher.log] == ["start", "end"] * 4


def test_a_stale_answer_is_dropped_and_its_job_run_alone(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    holder: dict[str, list[str]] = {}

    def recompute(core, job):                    # the logs change with each applied answer
        return {**job.inputs, "seen": len(holder["applied"])}

    core, dispatcher, applied = _setup(repo, monkeypatch, 3, recompute=recompute)
    holder["applied"] = applied
    made = _enqueue(core, 3)
    worker.run_once(core, "s1")
    assert applied == [j.id for j in made]       # each applied once, in the queue's order
    starts = [i for e, i in dispatcher.log if e == "start"]
    assert starts.count(made[0].id) == 1
    assert starts.count(made[1].id) == 2 and starts.count(made[2].id) == 2  # sent again alone



def test_unlocked_lets_go_of_the_guard_only_while_its_method_is_out() -> None:
    guard = threading.Lock()

    class Client:
        last_error = "none"

        def judge(self, request: str) -> tuple[str, bool]:
            return request, guard.locked()

    client = dispatch.Unlocked(Client(), guard, "judge")
    with guard:
        assert client.judge("q") == ("q", False)     # out: the guard is free
        assert guard.locked()                        # back: held again
    assert client.last_error == "none"               # everything else passes through
