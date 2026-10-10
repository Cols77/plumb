"""SR-104: the queue side (hooks queue and return; the same inputs are one job)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from plumb.api import Core
from plumb.contracts import JobResult
from plumb.understand import files, jobs, ledger, queue, worker

pytestmark = pytest.mark.sr("SR-104")


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "start_detached",
                        lambda root, session: calls.append((str(root), session)))
    return calls


def _count(repo: Path, session: str = "s1") -> int:
    return len(list(files.jobs_dir(repo, session).glob("*.json")))


def test_ex4_same_inputs_queued_twice_run_once(repo: Path, spawned,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import dispatch
    from understand.fakes import FakeDispatcher, FakeKind, fake_kinds

    fake = FakeDispatcher({"read": {"ok": True}})
    monkeypatch.setattr(dispatch, "configured", lambda core: fake)
    fake_kinds(monkeypatch, {"read": FakeKind("read")})
    core = Core(repo)
    one = jobs.new_job("read", "s1", "read.v1", {"n": 1})
    queue.enqueue(core, one)
    queue.enqueue(core, jobs.new_job("read", "s1", "read.v1", {"n": 1}))
    assert _count(repo) == 1
    on_disk = json.loads(jobs.job_path(repo, "s1", one.id).read_text(encoding="utf-8"))
    assert on_disk["id"] == one.id and on_disk["inputs"] == {"n": 1} and on_disk["created"]
    assert on_disk["needs"] is None and on_disk["v"] == 1
    assert spawned and spawned[0][1] == "s1"        # the worker is asked for, never waited for
    assert worker.run_once(core, "s1") == [one.id]
    assert worker.run_once(core, "s1") == [] and len(fake.jobs) == 1


def test_changed_inputs_new_job(repo: Path, spawned) -> None:
    core = Core(repo)
    queue.enqueue(core, jobs.new_job("read", "s1", "read.v1", {"n": 1}))
    queue.enqueue(core, jobs.new_job("read", "s1", "read.v1", {"n": 2}))
    assert _count(repo) == 2


def test_result_reused(repo: Path, spawned) -> None:
    core = Core(repo)
    job = jobs.new_job("read", "s1", "read.v1", {"n": 1})
    queue.enqueue(core, job)
    jobs.write_result(repo, "s1", JobResult(job=job.id, status="ok", answer={"a": 1}))
    ledger.record(repo, "s1", job.id)
    before = jobs.job_path(repo, "s1", job.id).read_bytes()
    spawned.clear()
    queue.enqueue(core, jobs.new_job("read", "s1", "read.v1", {"n": 1}))
    assert jobs.job_path(repo, "s1", job.id).read_bytes() == before
    assert jobs.pending(repo, "s1") == []            # nothing to run again
    assert spawned == []                             # and no worker asked for
    assert jobs.result(repo, "s1", job.id).answer == {"a": 1}


def test_enqueue_without_a_core_writes_nothing() -> None:
    assert queue.enqueue(None, jobs.new_job("read", "s1", "read.v1", {})) is None


def test_enqueue_does_not_wait_for_the_worker(repo: Path, monkeypatch: pytest.MonkeyPatch
                                              ) -> None:
    """SR-104 EX-1 on the queue side: whatever the worker does, the hook's call returns."""
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    core = Core(repo)
    best = 1e9
    for n in range(5):
        job = jobs.new_job("read", "s1", "read.v1", {"n": n})
        start = time.perf_counter()
        queue.enqueue(core, job)
        best = min(best, time.perf_counter() - start)
    assert best < 0.8 * 0.9
