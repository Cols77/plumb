"""SR-104 EX-10 to EX-12 (and SR-101 EX-13): the worker says in plain words what it is doing."""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

import pytest

from plumb import log
from plumb.api import Core
from plumb.contracts import Applied
from plumb.present import owner_text
from plumb.progress import Reporter, status_text
from plumb.understand import dispatch, files, jobs, queue, worker
from understand.fakes import FakeDispatcher, FakeKind, fake_kinds, owner_level

pytestmark = pytest.mark.sr("SR-273", "SR-214")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDispatcher:
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(dispatch, "configured", lambda core: dispatcher)
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    return dispatcher


def _job(kind: str, n: int = 1):
    return jobs.new_job(kind, "s1", f"{kind}.v1", {"n": n})


def _run_in_thread(core: Core) -> threading.Thread:
    thread = threading.Thread(target=worker.run_once, args=(core, "s1"), daemon=True)
    thread.start()
    return thread


def _config(repo: Path, interval: float) -> None:
    (repo / ".plumb" / "config.yaml").write_text(
        f"understand:\n  progress_interval_s: {interval}\n", encoding="utf-8")


def test_ex10_status_text_says_reading_your_answer_while_running_and_agent_carries_on(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import prompt

    gate = threading.Event()
    fake.block = gate
    fake_kinds(monkeypatch, {"read": FakeKind("read", describe=lambda job: owner_text.STEP_READING)})
    core = Core(repo)
    queue.enqueue(core, _job("read"))
    thread = _run_in_thread(core)
    try:
        assert fake.blocked.wait(10)
        assert status_text(repo, "s1") == "reading your answer"
        assert owner_level(status_text(repo, "s1")) == []
        # the agent carries on: a hook runs and returns while the model is still thinking
        payload = json.dumps({"session_id": "s1", "cwd": str(repo), "prompt": "carry on"})
        assert prompt.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo) == 0
        assert thread.is_alive()
        assert not list(log.read(core.paths, "events", ["approval", "verdict", "read-entry"]))
    finally:
        gate.set()
        thread.join(10)
    assert jobs.result(repo, "s1", _job("read").id).status == "ok"


def test_ex11_judging_7_records_then_line_gone(repo: Path, fake: FakeDispatcher,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    fake.block = gate
    fake_kinds(monkeypatch, {"judge": FakeKind(
        "judge", describe=lambda job: owner_text.STEP_JUDGING.format(n=7))})
    core = Core(repo)
    queue.enqueue(core, _job("judge"))
    thread = _run_in_thread(core)
    try:
        assert fake.blocked.wait(10)
        assert status_text(repo, "s1") == "judging 7 records"
        shown = files.progress_from_json(files.read_json(files.progress_path(repo, "s1")))
        assert shown.state == "running" and shown.kind == "judge" and shown.started
    finally:
        gate.set()
        thread.join(10)
    assert not files.progress_path(repo, "s1").exists()      # the line is gone
    assert status_text(repo, "s1") == ""


def test_the_step_is_reported_at_least_once_a_second(repo: Path, fake: FakeDispatcher,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _config(repo, 0.2)
    gate = threading.Event()
    fake.block = gate
    fake_kinds(monkeypatch, {"read": FakeKind("read", describe=lambda job: "reading your answer")})
    writes: list[str] = []
    original = Reporter.update

    def counting(self, step, done=0, total=0, *, state="running"):
        writes.append(state)
        return original(self, step, done, total, state=state)

    monkeypatch.setattr(Reporter, "update", counting)
    core = Core(repo)
    assert core.config.understand.progress_interval_s == 0.2
    queue.enqueue(core, _job("read"))
    thread = _run_in_thread(core)
    try:
        assert fake.blocked.wait(10)
        time.sleep(1.3)
    finally:
        gate.set()
        thread.join(10)
    assert writes.count("running") >= 4                      # well above once a second


def test_ex12_failed_job_names_the_step_and_stops_running(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"read": FakeKind("read", describe=lambda job: owner_text.STEP_READING)})
    fake.failing("timeout", "no answer within 120 seconds")
    core = Core(repo)
    queue.enqueue(core, _job("read"))
    worker.run_once(core, "s1")
    shown = files.progress_from_json(files.read_json(files.progress_path(repo, "s1")))
    assert shown.state == "failed" and "reading your answer" in shown.step
    assert owner_level(shown.step) == []
    assert status_text(repo, "s1") == ""                     # nothing is running any more
    # a retry that works takes the failed line away
    fake.script = {"read": {}}
    queue.retry_failed(core, "s1")
    worker.run_once(core, "s1")
    assert not files.progress_path(repo, "s1").exists()


def test_end_line_written_by_apply_is_not_removed(repo: Path, fake: FakeDispatcher,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    end = owner_text.BACKLOG_DONE.format(judged=160, questions=3)

    def apply_judge(core, job, answer):
        Reporter(core.root, "s1", "judge").done(end)
        return Applied(job=job.id)

    fake_kinds(monkeypatch, {"judge": FakeKind(
        "judge", describe=lambda job: owner_text.STEP_JUDGING_BACKLOG, apply=apply_judge)})
    core = Core(repo)
    queue.enqueue(core, _job("judge"))
    worker.run_once(core, "s1")
    shown = files.progress_from_json(files.read_json(files.progress_path(repo, "s1")))
    assert shown.state == "done" and shown.step == end
