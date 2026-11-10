"""SR-298: records waiting on a judge are queued at session start and by the landing job, once
each, and the session start only spawns a process."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from iaso.api import open_core
from understand.fakes import FakeDispatcher
from understand.test_backlog import bulk, in_repo  # noqa: F401
from understand.test_judge_job import SESSION

pytestmark = pytest.mark.sr("SR-298")


def queued(repo: Path) -> int:
    from iaso.understand import files

    return len(list(files.jobs_dir(repo, SESSION).glob("*.json")))


def test_ex1_session_start_queues_every_waiting_record_in_a_spawned_process(
        repo: Path, write_record, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.understand import backlog

    bulk(repo, write_record, {f"feature {n}": 5 for n in range(1, 33)})   # 32 x 6 = 192 + ...
    core = open_core(repo)
    spawned: list[Any] = []
    monkeypatch.setenv("IASO_FAKE_DISPATCH", "1")
    monkeypatch.setattr("subprocess.Popen", lambda argv, **kw: spawned.append(argv))
    begun = time.monotonic()
    assert backlog.spawn(core, SESSION) is True                # the hook only spawns
    assert time.monotonic() - begun < 1.0 and queued(repo) == 0
    assert spawned and "backlog" in spawned[0]
    waiting = backlog.waiting(core, SESSION)
    started = backlog.queue_waiting(core, SESSION)             # what the process does
    assert started.records == len(waiting) >= 192
    assert queued(repo) == len(started.jobs) > 0


def test_ex3_a_record_already_queued_is_not_queued_twice(
        repo: Path, write_record, engine_standins) -> None:
    from iaso.understand import backlog, judge, queue

    ids = bulk(repo, write_record, {"alpha": 3})["alpha"]
    core = open_core(repo)
    queue.enqueue(core, judge.build(core, SESSION, records=ids[:2]))   # a job for two of them
    assert set(backlog.waiting(core, SESSION)) == set(ids[2:])
    again = backlog.queue_waiting(core, SESSION)
    assert again.records == len(ids) - 2 and queued(repo) == 2
    assert backlog.queue_waiting(core, SESSION).jobs == [] and queued(repo) == 2


def test_ex4_no_judge_says_one_line_and_changes_nothing(
        repo: Path, write_record, engine_standins) -> None:
    from iaso.understand import backlog

    bulk(repo, write_record, {"alpha": 3})
    engine_standins.dispatcher.reason = "no key for the judge model"
    core = open_core(repo)
    first = backlog.queue_waiting(core, SESSION)
    assert first.jobs == [] and "no key for the judge model" in first.line
    assert queued(repo) == 0
    assert backlog.queue_waiting(core, SESSION).line == ""       # said once
    assert isinstance(engine_standins.dispatcher, FakeDispatcher)


@pytest.mark.sr("SR-301")
def test_ex1_another_sessions_open_loop_is_left_to_its_own_gate(
        repo: Path, write_record, engine_standins) -> None:
    """SR-301 EX-1: session s2 runs a loop on INT-001: the backlog of this session (or of a
    landing) queues the other intent's records only."""
    from iaso.understand import backlog, cmd_intent, files

    ids = bulk(repo, write_record, {"alpha": 2, "beta": 2})
    path = cmd_intent.open_loop(repo, "s2", "sha256:" + "c" * 64)
    files.write_json_atomic(path, {**files.read_json(path), "intent": "INT-001"})
    core = open_core(repo)
    assert set(backlog.waiting(core, SESSION)) == set(ids["beta"])
    assert backlog.queue_waiting(core, SESSION).records == len(ids["beta"])


def test_ex1_the_session_start_queue_marks_no_pass_so_turn_ends_stay_fast(
        repo: Path, write_record, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-298 EX-1: the spawned process queues only; no pass is marked, so no turn end runs
    ``resume`` over the whole backlog afterwards."""
    from iaso.understand import backlog

    bulk(repo, write_record, {"alpha": 3})
    core = open_core(repo)
    spawned: list[Any] = []
    monkeypatch.setenv("IASO_FAKE_DISPATCH", "1")
    monkeypatch.setattr("subprocess.Popen", lambda argv, **kw: spawned.append(argv))
    assert backlog.spawn(core, SESSION) and "--queue-only" in spawned[0]
    assert backlog.queue_waiting(core, SESSION, mark=False).records == 4
    assert not backlog.marker_path(repo, SESSION).exists()
    assert backlog.resume(core, SESSION).jobs == []
