"""SR-104 EX-3 and EX-5: a model that cannot answer is reported, retried and never replaced by
a word rule; nothing is confirmed, settled or rejected on a failure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iaso import approvals, confirm, log
from iaso.api import Core
from iaso.contracts import Applied, DispatchError, NoModel
from iaso.understand import dispatch, files, jobs, queue, worker
from understand.fakes import FakeDispatcher, FakeKind, fake_kinds

pytestmark = pytest.mark.sr("SR-273")

SCHEMA = {"type": "object", "properties": {"items": {"type": "array"}}, "required": ["items"]}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDispatcher:
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(dispatch, "configured", lambda core: dispatcher)
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    return dispatcher


def _job(kind: str, n: int = 1, session: str = "s1", needs: str | None = None):
    return jobs.new_job(kind, session, f"{kind}.v1", {"n": n}, needs=needs,
                        created=f"2026-01-01T00:00:{n:02d}Z")


def test_ex3_unreachable_model_summary_says_not_checked_and_retries(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[str] = []
    fake_kinds(monkeypatch, {"a": FakeKind(
        "a", apply=lambda core, job, answer: applied.append(job.id) or Applied(job=job.id))})
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    fake.failing("run", "the model could not be reached")
    worker.run_once(core, "s1")
    (lost,) = queue.failures(core, "s1")
    assert lost.job == job.id and lost.status == "error"
    assert lost.error.step == "run" and "could not be reached" in lost.error.message
    assert applied == []                                  # nothing came of it
    # the next turn asks again; the model is back
    fake.script = {"a": {"ok": True}}
    assert queue.retry_failed(core, "s1") == [job.id]
    assert worker.run_once(core, "s1") == [job.id]
    assert queue.failures(core, "s1") == [] and applied == [job.id]
    assert jobs.result(repo, "s1", job.id).status == "ok"
    assert queue.retry_failed(core, "s1") == []           # nothing left to retry


def test_a_failed_needs_job_is_retried_before_its_dependent(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a"), "b": FakeKind("b")})
    core = Core(repo)
    first = _job("a")
    second = _job("b", needs=first.id)
    queue.enqueue(core, second)
    queue.enqueue(core, first)
    fake.failing()
    worker.run_once(core, "s1")
    assert {r.job for r in queue.failures(core, "s1")} == {first.id, second.id}
    fake.script = {}
    assert sorted(queue.retry_failed(core, "s1")) == sorted([first.id, second.id])
    assert worker.run_once(core, "s1") == [first.id, second.id]
    assert queue.failures(core, "s1") == []


def test_ex5_word_rules_not_called_when_dispatcher_fails(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("a word rule was called after the model failed")

    for owner, name in ((approvals, "affirmation_context_problem"), (approvals, "owner_scope"),
                        (approvals, "quote_in_prompt"), (confirm, "affirmation_in"),
                        (confirm, "checked_entries")):
        monkeypatch.setattr(owner, name, boom, raising=False)
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    fake.failing("timeout", "no answer within 120 seconds")
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    worker.run_once(core, "s1")
    queue.retry_failed(core, "s1")
    worker.run_once(core, "s1")
    assert not list(log.read(core.paths, "events", ["approval", "revocation", "verdict"]))
    assert jobs.result(repo, "s1", job.id).error.step == "timeout"


def test_no_second_route(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One dispatcher is asked, once per attempt; no other is tried when it fails."""
    asked: list[str] = []

    class Failing(FakeDispatcher):
        def run(self, job, **kwargs):
            asked.append(self.name)
            raise DispatchError("run", "down")

    class Other(FakeDispatcher):
        def run(self, job, **kwargs):
            asked.append("second route")
            return {}

    monkeypatch.setattr(dispatch, "configured", lambda core: Failing(name="claude-code"))
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    for path in ("iaso.understand.dispatch.hermes", "iaso.understand.dispatch.openrouter"):
        try:
            module = __import__(path, fromlist=["x"])
        except ImportError:
            continue
        for attr in dir(module):
            if attr.endswith("Dispatcher"):
                monkeypatch.setattr(module, attr, Other)
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    queue.enqueue(core, _job("a"))
    worker.run_once(core, "s1")
    assert asked == ["claude-code"]


def test_no_model_configured_is_an_error_result(repo: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    def none(core):
        raise NoModel("no model configured")

    monkeypatch.setattr(dispatch, "configured", none)
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    worker.run_once(core, "s1")
    result = jobs.result(repo, "s1", job.id)
    assert result.status == "error" and result.error.step == "dispatch"


def test_three_failures_flagged(repo: Path, fake: FakeDispatcher,
                                monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    assert queue.consecutive_failures(repo, "s1") == 0
    fake.failing("run", "down")
    for n in (1, 2, 3):
        queue.enqueue(core, _job("a", n))
        worker.run_once(core, "s1")
        assert queue.consecutive_failures(repo, "s1") == n
    data = json.loads(files.failures_path(repo, "s1").read_text(encoding="utf-8"))
    assert data["v"] == 1 and data["consecutive"] == 3
    assert data["last"]["kind"] == "a" and data["last"]["step"] == "run"
    assert data["last"]["job"] == _job("a", 3).id and data["last"]["at"]
    fake.script = {"a": {"ok": True}}
    queue.enqueue(core, _job("a", 4))
    worker.run_once(core, "s1")
    assert queue.consecutive_failures(repo, "s1") == 0     # an ok result resets it
    assert queue.consecutive_failures(repo, "other") == 0


def test_failures_lists_error_results_without_a_later_ok(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    fake.failing()
    for n in (2, 1):
        queue.enqueue(core, _job("a", n))
    worker.run_once(core, "s1")
    listed = queue.failures(core, "s1")
    assert {r.job for r in listed} == {_job("a", 1).id, _job("a", 2).id}
    assert listed == sorted(listed, key=lambda r: (r.started, r.job))      # oldest first
    fake.script = {"a": {"ok": True}}
    queue.retry_failed(core, "s1")
    worker.run_once(core, "s1")
    assert queue.failures(core, "s1") == []


def test_schema_failure_is_an_error_not_a_reading(repo: Path, fake: FakeDispatcher,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[str] = []
    fake_kinds(monkeypatch, {"a": FakeKind(
        "a", schema=SCHEMA,
        apply=lambda core, job, answer: applied.append(job.id) or Applied(job=job.id))})
    fake.script = {"a": {"items": "not a list"}}
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    worker.run_once(core, "s1")
    result = jobs.result(repo, "s1", job.id)
    assert result.status == "error" and result.error.step == "schema" and result.answer is None
    assert applied == []
    assert queue.consecutive_failures(repo, "s1") == 1
    fake.script = {"a": {"other": 1}}                       # a missing key fails too
    queue.retry_failed(core, "s1")
    worker.run_once(core, "s1")
    assert jobs.result(repo, "s1", job.id).error.step == "schema" and applied == []


def test_a_failing_apply_is_an_error_and_writes_nothing(
        repo: Path, fake: FakeDispatcher, monkeypatch: pytest.MonkeyPatch) -> None:
    def apply_a(core, job, answer):
        raise RuntimeError("the kind could not apply")

    fake_kinds(monkeypatch, {"a": FakeKind("a", apply=apply_a)})
    core = Core(repo)
    job = _job("a")
    queue.enqueue(core, job)
    worker.run_once(core, "s1")
    result = jobs.result(repo, "s1", job.id)
    assert result.status == "error" and result.error.step == "apply"
    assert not list(log.read(core.paths, "events", ["approval"]))


def test_retry_and_failures_do_nothing_inside_a_job(repo: Path, fake: FakeDispatcher,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    queue.enqueue(core, _job("a"))
    fake.failing()
    worker.run_once(core, "s1")
    monkeypatch.setenv("IASO_JOB", "read-0123456789abcdef")
    assert queue.retry_failed(core, "s1") == []
    assert len(queue.failures(core, "s1")) == 1


def _core_with(dispatch_name: str):
    from types import SimpleNamespace

    from iaso.config import UnderstandConfig

    return SimpleNamespace(config=SimpleNamespace(
        understand=UnderstandConfig(dispatch=dispatch_name)), root=Path("."))


def test_configured_returns_exactly_one_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.understand.dispatch.claude_code import ClaudeCodeDispatcher

    with pytest.raises(NoModel, match="no model configured"):
        dispatch.configured(_core_with("auto"))              # neither host: an error
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/somewhere")
    assert isinstance(dispatch.configured(_core_with("auto")), ClaudeCodeDispatcher)
    assert isinstance(dispatch.configured(_core_with("claude-code")), ClaudeCodeDispatcher)
    with pytest.raises(NoModel, match="no model configured"):
        dispatch.configured(_core_with("carrier-pigeon"))
    monkeypatch.setenv("IASO_FAKE_DISPATCH", "script.json")
    assert dispatch.configured(_core_with("claude-code")).name == "fake"


def test_scripted_dispatcher_answers_by_kind(tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"read": {"items": []}, "judge": {"error": "down"}}),
                      encoding="utf-8")
    scripted = dispatch.ScriptedDispatcher(script)
    assert scripted.available() is None
    assert scripted.run(_job("read"), system="", user="", schema={},
                        on_step=lambda s: None) == {"items": []}
    with pytest.raises(DispatchError):
        scripted.run(_job("judge"), system="", user="", schema={}, on_step=lambda s: None)
    assert dispatch.ScriptedDispatcher(tmp_path / "missing.json").available()
