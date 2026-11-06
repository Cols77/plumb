"""SR-104: the worker runs queued jobs, one worker per session, jobs in the order of ``needs``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from plumb import log
from plumb.api import Core
from plumb.contracts import Applied, DispatchError, Job
from plumb.understand import dispatch, files, jobs, ledger, queue, worker
from understand.fakes import FakeDispatcher, FakeKind, fake_kinds

pytestmark = pytest.mark.sr("SR-273", "SR-223")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDispatcher:
    """The worker's dispatcher is a fake; no process is started for a queued job."""
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(dispatch, "configured", lambda core: dispatcher)
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    return dispatcher


def _job(kind: str, n: int = 1, *, needs: str | None = None, created: str | None = None,
         session: str = "s1") -> Job:
    return jobs.new_job(kind, session, f"{kind}.v1", {"n": n}, needs=needs, created=created)


def _notes(core: Core) -> list[dict]:
    return [dict(e.payload) for e in log.read(core.paths, "events", ["job-note"])]


def test_runs_queued_job_once(repo: Path, fake: FakeDispatcher,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[str] = []
    fake_kinds(monkeypatch, {"a": FakeKind(
        "a", apply=lambda core, job, answer: applied.append(job.id) or Applied(job=job.id))})
    fake.script = {"a": {"ok": True}}
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    assert worker.run_once(core, "s1") == [job.id]
    assert worker.run_once(core, "s1") == []
    assert applied == [job.id] and [j.id for j in fake.jobs] == [job.id]
    result = jobs.result(repo, "s1", job.id)
    assert result.status == "ok" and result.answer == {"ok": True}
    assert result.dispatcher == "fake" and result.started and result.finished
    assert ledger.has(repo, "s1", job.id)


def test_an_answer_queued_during_the_backlog_runs_before_its_remaining_jobs(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner's answer arrives while the backlog pass runs: it goes next, not last."""
    # one at a time (understand.parallel_calls: 1): what this test is about
    with (repo / ".plumb" / "config.yaml").open("a", encoding="utf-8") as fh:
        fh.write("\nunderstand:\n  parallel_calls: 1\n")
    core = Core(repo)
    first, second = (jobs.new_job("a", "s1", "a.v1", {"pass": "backlog", "n": n},
                                  created=f"2026-01-01T00:00:0{n}Z") for n in (1, 2))
    answer = _job("b", created="2026-01-01T00:00:05Z")
    fake_kinds(monkeypatch, {
        "a": FakeKind("a", apply=lambda c, job, a: (
            queue.enqueue(c, answer) if job.id == first.id else None) or Applied(job=job.id)),
        "b": FakeKind("b")})
    for job in (first, second):
        queue.enqueue(core, job)
    assert worker.run_once(core, "s1") == [first.id, answer.id, second.id]


def test_a_given_job_runs_alone_with_its_needs(repo: Path, fake: FakeDispatcher,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a"), "b": FakeKind("b")})
    core = Core(repo)
    first, other = _job("a", 1), _job("a", 2)
    second = _job("b", 1, needs=first.id)
    for job in (other, second, first):
        queue.enqueue(core, job)
    assert worker.run_once(core, "s1", second.id) == [first.id, second.id]
    assert jobs.result(repo, "s1", other.id) is None


def test_one_worker_per_session(repo: Path) -> None:
    mine = worker.acquire(repo, "s1")
    assert mine and len(mine) == 32
    assert worker.acquire(repo, "s1") is None          # held by this one
    assert worker.acquire(repo, "s2")                  # another session is free
    worker.release(repo, "s1", mine)
    assert worker.acquire(repo, "s1")


def test_another_live_process_holding_the_lock_runs_nothing(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        files.write_json_atomic(files.lock_path(repo, "s1"), {
            "pid": other.pid, "heartbeat": time.time(), "token": "c3" * 16})
        core = Core(repo)
        queue.enqueue(core, _job("a"))
        assert worker.run_once(core, "s1") == [] and fake.jobs == []
        assert worker.acquire(repo, "s1") is None
    finally:
        other.kill()
        other.wait()


def test_stale_lock_taken_over(repo: Path) -> None:
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        files.write_json_atomic(files.lock_path(repo, "s1"), {
            "pid": other.pid, "heartbeat": time.time() - 3600, "token": "c3" * 16})
        token = worker.acquire(repo, "s1")                 # alive but silent: taken over
        assert token and token != "c3" * 16
        held = json.loads(files.lock_path(repo, "s1").read_text(encoding="utf-8"))
        assert held["token"] == token
    finally:
        other.kill()
        other.wait()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    files.write_json_atomic(files.lock_path(repo, "s2"), {
        "pid": dead.pid, "heartbeat": time.time(), "token": "d4" * 16})
    assert worker.acquire(repo, "s2")                      # its process is gone


def test_job_waits_for_its_needs_then_runs(repo: Path, fake: FakeDispatcher,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def apply_a(core, job, answer):
        seen.append("apply-a")
        return Applied(job=job.id)

    def recompute_b(core, job):
        seen.append("recompute-b")
        return dict(job.inputs)

    fake_kinds(monkeypatch, {"a": FakeKind("a", apply=apply_a),
                             "b": FakeKind("b", recompute=recompute_b)})
    core = Core(repo)
    for order in ("b-first", "a-first"):
        session = f"s-{order}"
        a = _job("a", 1, created="2026-01-02T00:00:00Z", session=session)
        b = _job("b", 1, needs=a.id, created="2026-01-01T00:00:00Z", session=session)
        steps = [b, a] if order == "b-first" else [a, b]
        for job in steps:
            queue.enqueue(core, job)
        seen.clear()
        fake.jobs.clear()
        assert worker.run_once(core, session) == [a.id, b.id]
        assert [j.kind for j in fake.jobs] == ["a", "b"]
        assert seen == ["apply-a", "recompute-b"]
        assert jobs.result(repo, session, a.id).status == "ok"


def test_dependent_recompute_sees_what_the_needs_job_applied(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-103 EX-9: the clarifier is asked after the reader's cards were applied."""
    def apply_a(core, job, answer):
        return Applied(job=job.id, entries=({"kind": "job-note", "payload": {
            "kind": "a", "job": job.id, "detail": "card answered"}},))

    def recompute_b(core, job):
        answered = [e.payload["detail"] for e in log.read(core.paths, "events", ["job-note"])
                    if e.payload.get("kind") == "a"]
        return {"answered": answered}

    fake_kinds(monkeypatch, {"a": FakeKind("a", apply=apply_a),
                             "b": FakeKind("b", recompute=recompute_b)})
    core = Core(repo)
    a = _job("a")
    b = _job("b", needs=a.id)
    queue.enqueue(core, b)
    queue.enqueue(core, a)
    worker.run_once(core, "s1")
    (call,) = [c for c in fake.calls if c["kind"] == "b"]
    assert "card answered" in call["user"]


def test_needs_job_failed_dependent_is_an_error_and_the_model_is_not_called(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a"), "b": FakeKind("b")})
    fake.script = lambda job: DispatchError("run", "unreachable") if job.kind == "a" else {}
    core = Core(repo)
    a = _job("a")
    b = _job("b", needs=a.id)
    queue.enqueue(core, a)
    queue.enqueue(core, b)
    worker.run_once(core, "s1")
    assert [j.kind for j in fake.jobs] == ["a"]
    result = jobs.result(repo, "s1", b.id)
    assert result.status == "error" and result.error.step == "needs"
    assert jobs.result(repo, "s1", a.id).error.step == "run"


def test_needs_without_job_file_or_result_is_satisfied_and_noted(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"b": FakeKind("b")})
    core = Core(repo)
    b = _job("b", needs="a-0123456789abcdef")
    queue.enqueue(core, b)
    assert worker.run_once(core, "s1") == [b.id]
    assert jobs.result(repo, "s1", b.id).status == "ok"
    assert any(n["job"] == b.id and "a-0123456789abcdef" in n["detail"] for n in _notes(core))


def test_unknown_kind_is_an_error_result(repo: Path, fake: FakeDispatcher) -> None:
    core = Core(repo)
    job = _job("nosuchkind")
    queue.enqueue(core, job)
    worker.run_once(core, "s1")
    result = jobs.result(repo, "s1", job.id)
    assert result.status == "error" and result.error.step == "kind"
    assert fake.jobs == []


def test_a_kind_with_nothing_to_ask_is_skipped_without_the_model(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a", recompute=lambda core, job: None)})
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    assert worker.run_once(core, "s1") == [job.id]
    assert fake.jobs == [] and jobs.result(repo, "s1", job.id).status == "ok"


def test_a_test_that_queues_a_job_starts_no_process(repo: Path) -> None:
    core = Core(repo)
    job = jobs.new_job("read", "s1", "read.v1", {"n": 1})
    queue.enqueue(core, job)
    time.sleep(0.5)
    assert not files.lock_path(repo, "s1").exists() and jobs.result(repo, "s1", job.id) is None


def test_run_loop_picks_up_jobs_queued_while_it_runs(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    core = Core(repo)
    later = _job("a", 2)

    def apply_a(c, job, answer):
        if job.id != later.id:
            queue.enqueue(c, later)
        return Applied(job=job.id)

    fake_kinds(monkeypatch, {"a": FakeKind("a", apply=apply_a)})
    first = _job("a", 1)
    queue.enqueue(core, first)
    worker.run_loop(core, "s1")
    assert jobs.result(repo, "s1", first.id) and jobs.result(repo, "s1", later.id)
    assert not files.lock_path(repo, "s1").exists()        # the lock is let go at the end


def test_start_detached_runs_the_queue_in_another_process(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real detached worker runs the queued job in another process and it ends ok."""
    script = repo / "script.json"
    # READ landed: its answer must hold the entries list the schema asks for (none here)
    script.write_text('{"read": {"entries": []}}', encoding="utf-8")
    monkeypatch.setenv("PLUMB_FAKE_DISPATCH", str(script))   # under pytest only then it spawns
    core = Core(repo)
    job = jobs.new_job("read", "s1", "read.v1", {"n": 1})
    queue.enqueue(core, job)                              # asks for the worker itself
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline and not (
            jobs.result(repo, "s1", job.id) and not files.lock_path(repo, "s1").exists()):
        time.sleep(0.2)
    result = jobs.result(repo, "s1", job.id)
    assert result is not None and result.status == "ok"
    assert os.environ.get("PLUMB_WORKER") is None


def test_cmd_worker_runs_the_session_in_the_foreground(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    from plumb.understand import cmd_worker

    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    assert cmd_worker.run("understand", ["worker", "--session", "s1", "--root", str(repo)]) == 0
    assert jobs.result(repo, "s1", job.id).status == "ok"
    assert cmd_worker.run("understand", []) == 2
    assert "not available in this build" in capsys.readouterr().err


@pytest.mark.sr("SR-223")
def test_an_applied_entry_is_seen_by_the_next_job_on_the_same_core(repo: Path) -> None:
    """SR-131 EX-4: the reader's entries reach a later job applied by the same worker (the
    request check reads them to keep a card open on a vague answer)."""
    core = Core(repo)
    assert not [e for e in core.events() if e.kind == "read-entry"]    # cached now
    worker._write_applied(core, "s1", Applied(job="r1", entries=(
        {"kind": "read-entry", "payload": {"id": "choice:x/q", "answer": "open"}},)))
    assert [e.payload["answer"] for e in core.events() if e.kind == "read-entry"] == ["open"]
