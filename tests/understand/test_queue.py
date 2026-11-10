"""SR-104: the queue side (hooks queue and return; the same inputs are one job)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from iaso.api import Core
from iaso.contracts import JobResult
from iaso.understand import files, jobs, ledger, queue, worker

pytestmark = pytest.mark.sr("SR-273")


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
    from iaso.understand import dispatch
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


def _prompt_payload(repo: Path, text: str) -> str:
    return json.dumps({"session_id": "s1", "cwd": str(repo), "prompt": text})


def test_ex1_prompt_hook_returns_within_budget_without_waiting(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook queues the read job and returns; the worker (blocked here for good) is not
    waited for. Minimum of several runs against the budget times 0.9."""
    import io
    import threading

    from iaso.hosts.claude_code import hookio, prompt
    from iaso.understand import dispatch, read
    from understand.fakes import FakeDispatcher, FakeKind, fake_kinds

    blocked = FakeDispatcher({"read": {}}, block=threading.Event())
    monkeypatch.setattr(dispatch, "configured", lambda core: blocked)
    fake_kinds(monkeypatch, {"read": FakeKind("read")})
    started: list[str] = []
    monkeypatch.setattr(worker, "start_detached",
                        lambda root, session: started.append(session))

    def on_prompt(ctx, core, entry):
        job = jobs.new_job("read", "s1", "read.v1", {"message": str(entry["text"])})
        queue.enqueue(core, job)
        return job.id

    monkeypatch.setattr(read, "on_prompt", on_prompt)
    budget = hookio.hook_budget("prompt")(repo)
    best = 1e9
    for n in range(4):
        out = io.StringIO()
        start = time.perf_counter()
        assert prompt.main(stdin=io.StringIO(_prompt_payload(repo, f"please change {n}")),
                           stdout=out, root=repo) == 0
        best = min(best, (time.perf_counter() - start) * 1000)
    assert best < 0.9 * budget
    reads = list(files.jobs_dir(repo, "s1").glob("read-*.json"))   # (a clarify job each too)
    assert len(reads) == 4 and started                        # queued, worker asked for
    assert blocked.jobs == []                                 # and the hook never ran a job


def test_one_job_per_turn_one_per_capture_with_fake_kinds(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One read job covers every shown record of a turn; one judge job per capture."""
    import io

    from iaso.capture import capture as capture_module
    from iaso.hosts.claude_code import prompt
    from iaso.understand import judge, read
    from understand.fakes import FakeKind, fake_kinds

    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    shown = [{"id": f"SR-00{n}", "hash": f"sha256:{n}", "text": f"record {n}"}
             for n in range(1, 8)]

    def build(core, session, **context):
        return jobs.new_job("read", session, "read.v1",
                            {"message": context["message"], "shown": shown})

    fake_kinds(monkeypatch, {"read": FakeKind("read", build=build)})

    def on_prompt(ctx, core, entry):
        from iaso.understand.kinds import KINDS

        job = KINDS["read"].build(core, "s1", message=str(entry["text"]))
        queue.enqueue(core, job)
        return job.id

    monkeypatch.setattr(read, "on_prompt", on_prompt)

    def queue_for_capture(core, result, prompt_digest=None):
        queue.enqueue(core, jobs.new_job("judge", "s1", "judge.v1",
                                         {"digest": prompt_digest, "result": str(id(result))}))

    monkeypatch.setattr(judge, "queue_for_capture", queue_for_capture)
    for text in ("first thing", "second thing", "third thing"):
        assert prompt.main(stdin=io.StringIO(_prompt_payload(repo, text)),
                           stdout=io.StringIO(), root=repo) == 0
    reads = [j for j in jobs.queued(repo, "s1") if j.kind == "read"]
    assert len(reads) == 3 and all(len(j.inputs["shown"]) == 7 for j in reads)
    core = Core(repo)
    for digest in ("sha256:aa", "sha256:bb"):
        capture_module._understand_after(core, {}, object(), digest)
    assert len([j for j in jobs.queued(repo, "s1") if j.kind == "judge"]) == 2
    assert len([j for j in jobs.queued(repo, "s1") if j.kind in ("read", "judge")]) == 5
