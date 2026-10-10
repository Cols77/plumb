"""SP8 phase C: every contract and stub against its signature (plan 3.2 items 1 to 9)."""

from __future__ import annotations

import dataclasses
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from plumb import contracts
from plumb.contracts import (
    Applied,
    CardState,
    ClarifyAnswer,
    ClarifyQuestion,
    DispatchError,
    Dispatcher,
    GateState,
    Job,
    JobError,
    JobKind,
    JobResult,
    JudgeVerdict,
    NoModel,
    Progress,
    ReaderEntry,
    ReadCard,
    ReadItem,
    SettleState,
    StopParts,
)
from plumb.understand import files

pytestmark = pytest.mark.sr("SR-103", "SR-104", "SR-105")

DATA_CLASSES = (Job, JobError, JobResult, ReadItem, ReadCard, ReaderEntry, JudgeVerdict,
                ClarifyQuestion, ClarifyAnswer, CardState, Applied, GateState, SettleState,
                Progress, StopParts)


@pytest.mark.parametrize("cls", DATA_CLASSES, ids=lambda c: c.__name__)
def test_frozen_with_defaults_on_every_field(cls) -> None:
    item = cls()   # every field has a default
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(item, dataclasses.fields(cls)[0].name, "changed")


def test_job_needs_defaults_to_none_and_card_kinds_are_complete() -> None:
    assert Job().needs is None
    assert set(contracts.CARD_KINDS) == {
        "clarify", "trial", "backlog", "beyond", "contradicts", "couldnt_check", "show_first",
        "settle_offer", "settled_item", "link", "stale_link"}
    assert set(contracts.CardKind.__args__) == set(contracts.CARD_KINDS)
    assert "settled" in contracts.ApprovalBy.__args__ and \
        "owner-words" in contracts.ApprovalBy.__args__
    assert contracts.RecordStatus(id="SR-1", confirmation="proposed", approved_by=None,
                                  covered=False, uncovered_examples=(), links=()).settled \
        is False


def test_job_id_is_content_addressed_and_needs_changes_it() -> None:
    inputs = {"message": {"digest": "d", "text": "t"}}
    a = files.job_id("read", "read.v1", inputs, None)
    assert a == files.job_id("read", "read.v1", dict(inputs), None)
    assert a.startswith("read-") and len(a) == len("read-") + 16
    assert files.job_id("clarify", "clarify.v1", inputs, a) != \
        files.job_id("clarify", "clarify.v1", inputs, None)


def test_file_formats_round_trip() -> None:
    job = files.make_job("clarify", "s1", "clarify.v1", {"message": {"digest": "d"}},
                         needs="read-0123456789abcdef", created="2026-10-10T00:00:00Z")
    data = files.job_to_json(job)
    assert set(data) == {"v", "id", "kind", "session", "created", "schema", "needs", "inputs",
                         "inputs_digest"}
    assert files.job_from_json(json.loads(json.dumps(data))) == job
    result = JobResult(job=job.id, status="error", error=JobError("needs", "failed"),
                       model="m", dispatcher="fake", run_s=1.5)
    assert files.result_from_json(files.result_to_json(result)) == result
    gate = GateState(state="closed", message_digest="d", reason="r", since="t")
    assert files.gate_from_json(files.gate_to_json(gate)) == gate
    progress = Progress(step="reading your answer", done=1, total=3, state="running", kind="read")
    assert files.progress_from_json(files.progress_to_json(progress)) == progress


def test_committed_log_kinds_are_accepted(repo: Path) -> None:
    from plumb.api import open_core

    core = open_core(repo)
    payloads = {
        "premise": {"digest": "d", "text": "t", "session": "s", "used_by": []},
        "verdict": {"job": "j", "id": "SR-1", "hash": "h", "verdict": "supported",
                    "beyond": [], "contradicts": [], "score": 0.9, "model": "m",
                    "premise_digest": "d"},
        "read-entry": {"job": "j", "id": "SR-1", "hash": "h", "answer": "yes",
                       "confidence": 0.9, "evidence": "e", "message_digest": "d"},
        "revocation": {"by": "undone", "records": []},
        "settle-config": {"kind": "requirement", "on": True, "via": "typed",
                          "calibration": "c"},
        "trial": {"card": "c", "items": [], "answers": []},
        "eval-run": {"model": "m", "prompt_digest": "d", "cases": [], "passed": 0,
                     "false_gap_rate": 0.0},
        "gate": {"digest": "d", "state": "closed", "by": "clarify", "reason": "r"},
        "job-note": {"kind": "ledger", "job": "j", "detail": "no ledger entry"},
    }
    for kind, payload in payloads.items():
        assert core.log_append("events", kind, payload).kind == kind


def test_protocols_describe_the_dispatcher_and_the_kinds() -> None:
    run = inspect.signature(Dispatcher.run)
    assert list(run.parameters) == ["self", "job", "system", "user", "schema", "on_step"]
    assert [p.kind for n, p in run.parameters.items() if n in ("system", "user", "schema",
                                                                "on_step")] \
        == [inspect.Parameter.KEYWORD_ONLY] * 4
    assert list(inspect.signature(JobKind.build).parameters) == ["self", "core", "session",
                                                                 "context"]
    assert issubclass(DispatchError, Exception) and issubclass(NoModel, Exception)
    err = DispatchError("run", "boom")
    assert (err.step, err.message) == ("run", "boom")


@pytest.mark.parametrize("name", ["read", "judge", "clarify"])
def test_every_kind_stub_follows_the_job_kind_protocol(name: str) -> None:
    from plumb.understand.kinds import KINDS

    module = KINDS[name]
    assert module.kind == name and "id" in module.schema
    job = Job(id=f"{name}-0", kind=name)
    assert module.build(None, "s1") is None
    assert module.recompute(None, job) is None
    assert module.apply(None, job, {}) == Applied(job=job.id)
    assert isinstance(module.describe(job), str) and module.describe(job)
    for func, params in ((module.build, ["core", "session", "context"]),
                         (module.recompute, ["core", "job"]),
                         (module.apply, ["core", "job", "answer"]),
                         (module.describe, ["job"])):
        assert list(inspect.signature(func).parameters) == params


def test_kinds_maps_the_three_kinds() -> None:
    from plumb.understand.kinds import KINDS

    assert sorted(KINDS) == ["clarify", "judge", "read"]


def _params(func) -> list[str]:
    return list(inspect.signature(func).parameters)


def test_stub_signatures_and_behaviour(tmp_path: Path) -> None:
    from plumb.understand import (
        clarify,
        dispatch,
        gate,
        hooks,
        judge,
        premise,
        queue,
        read,
        summary,
        worker,
    )

    assert _params(read.on_prompt) == ["ctx", "core", "entry"]
    assert read.on_prompt(None, None, {}) is None
    assert _params(clarify.on_prompt) == ["ctx", "core", "entry", "after"]
    assert clarify.on_prompt(None, None, {}, after="read-0") == []
    assert _params(judge.queue_for_capture) == ["core", "result", "prompt_digest"]
    assert judge.queue_for_capture(None, None) is None
    assert _params(premise.commit) == ["core", "doc", "result", "prompt_digest"]
    assert premise.commit(None, {}, None) is None
    assert premise.problems(None) == [] and gate.problems(None) == []
    assert _params(queue.enqueue) == ["core", "job"]
    assert queue.enqueue(None, Job()) is None
    assert _params(queue.retry_failed) == ["core", "session"]
    assert _params(worker.start_detached) == ["root", "session"]
    assert worker.start_detached(tmp_path, "s1") is None
    assert _params(gate.is_closed) == ["root", "session"]
    assert gate.is_closed(tmp_path, "s1") is False
    assert _params(summary.stop_parts) == ["ctx", "core", "turn"]
    assert summary.stop_parts(None, None, {}) == StopParts()
    assert _params(hooks.on_prompt) == ["ctx", "core", "entry"]
    assert _params(dispatch.configured) == ["core"]
    with pytest.raises(NoModel, match="no model configured"):
        dispatch.configured(None)


def test_hooks_on_prompt_orders_read_then_clarify_and_never_raises(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import clarify, hooks, queue, read

    calls: list[object] = []
    monkeypatch.setattr(read, "on_prompt", lambda ctx, core, entry: calls.append("read")
                        or "read-0123456789abcdef")
    monkeypatch.setattr(clarify, "on_prompt", lambda ctx, core, entry, *, after=None:
                        calls.append(("clarify", after)) or ["a line"])
    monkeypatch.setattr(queue, "retry_failed", lambda core, session: calls.append("retry")
                        or [])
    assert hooks.on_prompt(None, None, {}) == ["a line"]
    assert calls == ["read", ("clarify", "read-0123456789abcdef"), "retry"]

    def boom(ctx, core, entry):
        raise RuntimeError("model layer broke")

    monkeypatch.setattr(read, "on_prompt", boom)
    assert hooks.on_prompt(None, None, {}) == []


def test_recheck_dispatches_by_value_and_refuses_hand_written_entries() -> None:
    from plumb.understand import recheck

    def entry(by: str, kind: str = "approval"):
        return contracts.LogEntry("events", kind, "t", "none", {"by": by}, None, "sha256:x")

    for by, kind in (("owner-words", "approval"), ("settled", "approval"),
                     ("undone", "revocation")):
        assert recheck.problem(entry(by, kind), None) == "not available in this build"
    assert recheck.problem(entry("owner"), None) is None


def test_confirm_entry_problem_calls_the_recheck_for_the_new_values() -> None:
    from plumb import confirm
    from plumb.log import entry_digest

    for by in ("owner-words", "settled"):
        raw = {"v": 1, "kind": "approval", "at": "t", "marker": "none",
               "payload": {"by": by, "records": []}, "prev": None}
        entry = contracts.LogEntry("events", "approval", "t", "none", raw["payload"], None,
                                   entry_digest(raw))
        assert confirm.entry_problem(entry, set(), ()) == "not available in this build"


def test_effects_registry() -> None:
    from plumb.understand import effects

    seen = []
    effects.register("test_kind", lambda *a: seen.append(a))
    handler = effects.handler_for("test_kind")
    assert handler is not None
    handler(1)
    assert seen == [(1,)]
    assert effects.handler_for("never_registered") is None
    effects.HANDLERS.pop("test_kind")


def test_config_section_understand(tmp_path: Path) -> None:
    from plumb.config import load_config

    u = load_config(tmp_path).understand
    assert (u.dispatch, u.model, u.timeout_s, u.clarify_wait_s) == ("auto", "haiku", 120, 45)
    assert (u.reader_threshold_start, u.backlog_cards_per_turn) == (0.9, 3)
    assert (u.progress_min_s, u.progress_interval_s, u.max_consecutive_failures) == (2, 1, 3)
    (tmp_path / ".plumb").mkdir()
    (tmp_path / ".plumb" / "config.yaml").write_text(
        "understand:\n  dispatch: hermes\n  timeout_s: 30\n", encoding="utf-8")
    u = load_config(tmp_path).understand
    assert (u.dispatch, u.timeout_s, u.model) == ("hermes", 30, "haiku")


def test_routes_and_help_list_only_importable_verbs() -> None:
    from plumb import cli

    for verb in ("understand", "settle", "undo", "go", "clarify"):
        assert cli.ROUTES[verb] == "plumb.understand.cli"
    assert cli._available("clarify")
    assert "clarify" in cli.help_text()
    saved = dict(cli.ROUTES)
    try:
        cli.ROUTES["settle"] = "plumb.no_such_module"
        assert "\n  settle" not in cli.help_text()
    finally:
        cli.ROUTES.update(saved)


def test_stub_commands_print_not_available_and_exit_2(capsys: pytest.CaptureFixture) -> None:
    from plumb.understand import cli

    for verb in ("understand", "settle", "undo", "go"):
        assert cli.run(verb, []) == 2
        assert "not available in this build" in capsys.readouterr().err


def test_pre_tool_hook_allows(repo: Path) -> None:
    done = subprocess.run([sys.executable, "-m", "plumb", "hook", "pre-tool", "--root",
                           str(repo)], input="{}", capture_output=True, text=True, cwd=repo)
    assert done.returncode == 0 and done.stdout == ""


def test_hook_inside_a_job_prints_and_queues_nothing(repo: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from plumb.hosts.claude_code import prompt

    monkeypatch.setenv("PLUMB_JOB", "read-0123456789abcdef")
    out = io.StringIO()
    payload = json.dumps({"session_id": "s1", "cwd": str(repo), "prompt": "add multiply"})
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo) == 0
    assert out.getvalue() == ""
    assert not (repo / ".plumb" / "session" / "prompts.jsonl").exists()
    assert not (repo / ".plumb" / "session" / "s1" / "jobs").exists()


def test_statusline_appends_the_running_step(repo: Path) -> None:
    import io

    from plumb.hosts.claude_code import statusline
    from plumb.progress import Reporter, status_text

    assert status_text(repo, "s1") == ""
    Reporter(repo, "s1", "read").update("reading your answer", 1, 2)
    assert status_text(repo, "s1") == "reading your answer"
    out = io.StringIO()
    statusline.main(root=repo, stdin=io.StringIO(json.dumps({"session_id": "s1"})), stdout=out)
    assert out.getvalue().strip().endswith("reading your answer")
    Reporter(repo, None, "settle").update("judging the backlog")   # a shell's own execution
    assert status_text(repo, "other") == "judging the backlog"


def test_prompt_hook_calls_the_understand_layer_in_order(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from plumb.hosts.claude_code import prompt
    from plumb.understand import hooks

    seen: list[dict] = []
    monkeypatch.setattr(hooks, "on_prompt", lambda ctx, core, entry: seen.append(entry)
                        or ["understand line"])
    out = io.StringIO()
    payload = json.dumps({"session_id": "s1", "cwd": str(repo), "prompt": "add multiply"})
    prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo)
    assert seen and seen[0]["text"] == "add multiply" and seen[0]["digest"]
    assert "understand line" in out.getvalue()
    # a failing layer never blocks the prompt
    monkeypatch.setattr(hooks, "on_prompt", lambda *a: (_ for _ in ()).throw(RuntimeError()))
    out = io.StringIO()
    prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo)
    assert "skipped" not in out.getvalue()


def test_stop_places_confirmations_settled_then_cards(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import stop
    from plumb.understand import summary

    monkeypatch.setattr(summary, "stop_parts", lambda ctx, core, turn: StopParts(
        confirmations=("C",), settled=("S",), cards=("K",)))
    assert stop.understand_parts(None, None, {}) == ["C", "S", "K"]
    monkeypatch.setattr(summary, "stop_parts", lambda *a: (_ for _ in ()).throw(OSError()))
    assert stop.understand_parts(None, None, {}) == []


def test_capture_calls_judge_and_premise_after_writing(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.capture import capture as cap
    from plumb.understand import judge, premise

    calls: list[str] = []
    monkeypatch.setattr(judge, "queue_for_capture",
                        lambda core, result, *, prompt_digest=None: calls.append("judge"))
    monkeypatch.setattr(premise, "commit",
                        lambda core, doc, result, *, prompt_digest=None: calls.append("premise"))
    cap._understand_after(None, {}, contracts.CaptureResult(), "d")
    assert calls == ["judge", "premise"]

    def boom(*a, **k):
        raise RuntimeError("judge broke")

    monkeypatch.setattr(judge, "queue_for_capture", boom)
    cap._understand_after(None, {}, contracts.CaptureResult(), "d")   # never raises


def test_owner_text_constants_exist() -> None:
    from plumb.present import owner_text as t

    for name in ("CARD_CLARIFY", "CARD_TRIAL", "CARD_BACKLOG", "CARD_BEYOND",
                 "CARD_CONTRADICTS", "CARD_COULDNT_CHECK", "SETTLED_LINE", "STEP_READING",
                 "STEP_CHECKING", "STEP_JUDGING", "STEP_JUDGING_BACKLOG", "GATE_BUILD_ANYWAY",
                 "GATE_WAIT", "SETTLE_REPLY"):
        assert isinstance(getattr(t, name), str) and getattr(t, name)
    assert "/plumb" not in t.SETTLE_REPLY and not t.bare_cli_verbs(t.SETTLE_REPLY)


def test_fakes_and_harness_work(tmp_path: Path) -> None:
    import threading

    from understand.fakes import FakeDispatcher, as_worker, fake_claude

    fake = FakeDispatcher({"read": {"items": []}, "judge": lambda job: {"n": job.id}})
    steps: list[str] = []
    assert fake.run(Job(id="read-1", kind="read"), system="s", user="u", schema={},
                    on_step=steps.append) == {"items": []}
    assert fake.run(Job(id="judge-1", kind="judge"), system="", user="", schema={},
                    on_step=steps.append) == {"n": "judge-1"}
    assert [j.id for j in fake.ran("judge")] == ["judge-1"] and steps
    fake.failing()
    with pytest.raises(DispatchError):
        fake.run(Job(id="read-2", kind="read"), system="", user="", schema={},
                 on_step=lambda s: None)
    gate = threading.Event()
    blocking = FakeDispatcher({"read": {}}, block=gate)
    gate.set()
    blocking.run(Job(id="r", kind="read"), system="", user="", schema={}, on_step=lambda s: None)
    assert blocking.blocked.is_set()
    with as_worker(tmp_path, "s1") as token:
        import os

        assert os.environ["PLUMB_WORKER"] == token
        lock = json.loads((tmp_path / ".plumb" / "session" / "s1" / "worker.lock")
                          .read_text(encoding="utf-8"))
        assert lock["token"] == token and {"pid", "heartbeat"} <= set(lock)
    import os

    assert "PLUMB_WORKER" not in os.environ
    claude = fake_claude(tmp_path / "bin", {"ok": True})
    done = subprocess.run(["claude", "-p", "hi"], input="stdin text", capture_output=True,
                          text=True, env=claude.env(), cwd=tmp_path, shell=sys.platform == "win32")
    assert json.loads(done.stdout) == {"ok": True}
    (call,) = claude.calls()
    assert call["argv"] == ["-p", "hi"] and call["stdin"] == "stdin text"
    assert Path(call["cwd"]).resolve() == tmp_path.resolve() and "PATH" in call["env"]


def test_harness_drives_the_real_hooks(repo: Path) -> None:
    from understand.harness import Session

    session = Session(repo)
    session.start()
    session.say("add multiply next to add")
    session.edit("src/calc.py")
    session.stop()
    assert session.worker_idle(2.0)
    assert isinstance(session.status_line(), str)


def test_evalrun_fake_writes_an_eval_run_entry(repo: Path, capsys: pytest.CaptureFixture) -> None:
    from plumb.api import open_core
    from plumb.understand import evalrun

    assert evalrun.run("eval", ["--fake", "--root", str(repo)]) == 0
    assert "0 cases" in capsys.readouterr().out
    (entry,) = [e for e in open_core(repo).events() if e.kind == "eval-run"]
    assert entry.payload["passed"] == 0 and entry.payload["model"] == "fake"
    assert entry.payload["prompt_digest"].startswith("sha256:")
    cases = [{"name": "c1", "inputs": {}, "expect": {"answer": "yes"}}]
    results = evalrun.run_cases(evalrun.FakeEvalDispatcher(), cases, "read")
    assert results[0]["passed"] is True
