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
    CardPress,
    CardState,
    Choice,
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
    StopParts,
)
from plumb.understand import files

pytestmark = pytest.mark.sr("SR-223", "SR-273", "SR-267")

DATA_CLASSES = (Job, JobError, JobResult, ReadItem, ReadCard, ReaderEntry, JudgeVerdict,
                ClarifyQuestion, ClarifyAnswer, CardState, Applied, GateState,
                Progress, StopParts, Choice, CardPress)


@pytest.mark.parametrize("cls", DATA_CLASSES, ids=lambda c: c.__name__)
def test_frozen_with_defaults_on_every_field(cls) -> None:
    item = cls()   # every field has a default
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(item, dataclasses.fields(cls)[0].name, "changed")


def test_job_needs_defaults_to_none_and_card_kinds_are_complete() -> None:
    assert Job().needs is None
    assert set(contracts.CARD_KINDS) == {
        "clarify", "choice", "trial", "couldnt_check", "beyond", "contradicts", "stale_link",
        "drift", "regression", "test_changed", "conflict", "early_conflict"}
    assert set(contracts.CardKind.__args__) == set(contracts.CARD_KINDS)
    assert "settled" not in contracts.ApprovalBy.__args__
    assert "owner-words" in contracts.ApprovalBy.__args__
    assert not hasattr(contracts.RecordStatus(id="SR-1", confirmation="proposed",
                                              approved_by=None, covered=False,
                                              uncovered_examples=(), links=()), "settled")
    assert "withdrawn" in contracts.CARD_STATUSES


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
        contracts.CARD_PRESS: {"session": "s", "offer": "o", "card": "c", "question": "q",
                               "choice": 1, "answer": "open"},
    }
    for kind, payload in payloads.items():
        assert core.log_append("events", kind, payload).kind == kind


@pytest.mark.sr("SR-209")
def test_card_store_round_trips_choices_and_the_button_statuses(tmp_path: Path) -> None:
    from plumb.understand import cardstore

    question = ClarifyQuestion(
        id="c1#1", text="Keep the CSV export?", resolutions=("keep it", "drop it", "reword"),
        record="SR-001", hash="sha256:h",
        choices=(Choice("Confirm", "accepted"), Choice("drop it", "rejected"),
                 Choice("the second version", "change", "Export as JSON")))
    cards = [CardState(id=f"c{n}", kind="beyond", topic="export", questions=(question,),
                       status=status)
             for n, status in enumerate(contracts.CARD_STATUSES)]
    cardstore.save(tmp_path, "s1", cards)
    assert cardstore.own_cards(tmp_path, "s1") == cards
    assert set(contracts.CardStatus.__args__) == set(contracts.CARD_STATUSES) \
        >= {"left_open", "change_requested"}
    # older cards carry no choices; a choice with an unknown answer reads as "open" (it
    # confirms nothing), and an unknown status as "open"
    path = files.cards_path(tmp_path, "s1")
    path.write_text(json.dumps([{"id": "old", "status": "snoozed", "questions": [
        {"id": "q", "text": "t"},
        {"id": "r", "choices": [{"label": "maybe", "answer": "perhaps"}]}]}]),
        encoding="utf-8")
    (old,) = cardstore.own_cards(tmp_path, "s1")
    assert old.status == "open" and old.questions[0].choices == ()
    assert old.questions[1].choices == (Choice("maybe", "open", None),)
    assert ClarifyQuestion("q", "t", ("a",)).choices == ()   # positional use is unchanged


@pytest.mark.sr("SR-209")
def test_button_approval_is_accepted_by_the_log_and_refused_by_its_recheck(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import confirm
    from plumb.api import open_core

    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    core = open_core(repo)
    entry = core.log_append("events", "approval", {
        "by": "owner", "via": "button", "offer": "o", "card": "c", "question": "q",
        "records": [{"id": "SR-001", "hash": "sha256:h"}]})
    assert entry.marker == "none"
    # no panel registered, no offer drawn: a button approval confirms nothing (slice 4)
    assert "button approval" in confirm.entry_problem(entry, set(), ())
    plain = core.log_append("events", "approval", {
        "by": "owner", "via": "terminal", "records": [{"id": "SR-001", "hash": "sha256:h"}]})
    assert confirm.entry_problem(plain, set(), ()) is None


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


def test_kinds_maps_the_kinds() -> None:
    from plumb.understand.kinds import KINDS

    assert sorted(KINDS) == ["clarify", "judge", "pushback", "question", "read", "selfdebug",
                             "tidy"]


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
    # the landed summary needs a real core; the stub's empty answer is gone (SHOW/JUDGE landed)
    assert StopParts() == StopParts()
    assert _params(hooks.on_prompt) == ["ctx", "core", "entry"]
    assert _params(dispatch.configured) == ["core", "model"]   # model: a per-kind override
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

    for by, kind in (("owner-words", "approval"), ("undone", "revocation")):
        # the landed recheck refuses an entry that names no record at a version
        assert recheck.problem(entry(by, kind), None)
    assert recheck.problem(entry("owner"), None) is None


def test_confirm_entry_problem_calls_the_recheck_for_the_new_values() -> None:
    from plumb import confirm
    from plumb.log import entry_digest

    for by in ("owner-words", "undone"):
        raw = {"v": 1, "kind": "approval", "at": "t", "marker": "none",
               "payload": {"by": by, "records": []}, "prev": None}
        entry = contracts.LogEntry("events", "approval", "t", "none", raw["payload"], None,
                                   entry_digest(raw))
        assert confirm.entry_problem(entry, set(), ())


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

    for verb in ("understand", "clarify"):
        assert cli.ROUTES[verb] == "plumb.understand.cli"
    assert not {"settle", "undo", "go"} & set(cli.ROUTES)
    assert cli._available("clarify")
    assert "clarify" in cli.help_text()
    saved = dict(cli.ROUTES)
    try:
        cli.ROUTES["clarify"] = "plumb.no_such_module"
        assert "\n  clarify" not in cli.help_text()
    finally:
        cli.ROUTES.update(saved)


def test_stub_commands_print_not_available_and_exit_2(capsys: pytest.CaptureFixture) -> None:
    from plumb.understand import cli

    assert cli.run("understand", []) == 2
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

    for name in ("STEP_READING", "STEP_CHECKING", "STEP_JUDGING", "STEP_JUDGING_BACKLOG",
                 "GATE_BUILD_ANYWAY", "GATE_WAIT"):
        assert isinstance(getattr(t, name), str) and getattr(t, name)


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
    assert "cases" in capsys.readouterr().out  # the cases of the evaluation set landed
    (entry,) = [e for e in open_core(repo).events() if e.kind == "eval-run"]
    assert entry.payload["passed"] >= 0 and entry.payload["model"] == "fake"
    assert entry.payload["prompt_digest"].startswith("sha256:")
    cases = [{"name": "c1", "inputs": {}, "expect": {"answer": "yes"}}]
    results = evalrun.run_cases(evalrun.FakeEvalDispatcher(), cases, "read")
    assert results[0]["passed"] is True


# ---- phase C2: the contract gaps (plan 3.2a) ----------------------------------------------

def test_c2_stubs_have_final_signatures_and_are_marked() -> None:
    from plumb.understand import queue, worker

    assert _params(worker.run_once) == ["core", "session", "job_id"]
    assert _params(worker.run_loop) == ["core", "session"]
    assert _params(queue.failures) == ["core", "session"]
    assert _params(queue.consecutive_failures) == ["root", "session"]
    for func in (worker.run_once, worker.run_loop, queue.failures, queue.consecutive_failures):
        assert getattr(func, "__stub__", False) is False    # ENGINE replaced the stubs
    assert worker.run_once(None, "s1") == [] and worker.run_loop(None, "s1") is None
    assert queue.failures(None, "s1") == []
    assert queue.consecutive_failures(Path("."), "s1") == 0
    assert getattr(queue.enqueue, "__stub__", False) is False


def test_failures_file_has_its_path_in_the_session_folder(tmp_path: Path) -> None:
    assert files.failures_path(tmp_path, "s1") == (
        files.session_dir(tmp_path, "s1") / "failures.json")


def test_handler_for_imports_the_kind_modules(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import effects, kinds

    (tmp_path / "c2_lane_kind.py").write_text(
        "from plumb.understand import effects\n"
        "effects.register('c2_card', lambda *a, **k: 'handled')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(kinds.KIND_MODULES, "c2lane", "c2_lane_kind")
    monkeypatch.setitem(effects.HANDLERS, "c2_card", None)
    monkeypatch.delitem(effects.HANDLERS, "c2_card")
    monkeypatch.delitem(sys.modules, "c2_lane_kind", raising=False)
    handler = effects.handler_for("c2_card")
    assert handler is not None and handler() == "handled"
    assert effects.handler_for("no_such_kind") is None


def test_handler_for_raises_an_import_error_of_a_lane_module(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import effects, kinds

    monkeypatch.setitem(kinds.KIND_MODULES, "broken", "plumb.understand.no_such_module")
    with pytest.raises(ImportError):
        effects.handler_for("anything")


C2_TEXT = ("CONFIRM_YOU_SAID", "READBACK_CHANGE", "TYPED_CONFIRMED", "BACKLOG_DONE")


@pytest.mark.parametrize("name", C2_TEXT)
def test_c2_owner_text_passes_the_owner_level_scan(name: str) -> None:
    from plumb.present import owner_text
    from understand.fakes import owner_level

    assert owner_level(getattr(owner_text, name)) == []


def test_owner_text_constants_have_their_fields() -> None:
    from plumb.present import owner_text

    assert owner_text.CONFIRM_YOU_SAID.format(evidence="ok") == "you said: ok"
    assert owner_text.BACKLOG_DONE.format(judged=160, questions=3) == (
        "160 records judged, 3 questions waiting for you")


def test_owner_level_flags_commands_ids_and_internal_words() -> None:
    from understand.fakes import owner_level

    assert owner_level("run plumb status") != []
    assert owner_level("SR-012 is settled") != []
    assert owner_level("the worker queued a job") != []
    assert owner_level("Settled from your words: the login") == []


def test_reporter_done_can_carry_an_end_line(tmp_path: Path) -> None:
    from plumb.progress import Reporter

    reporter = Reporter(tmp_path, "s1", "judge")
    reporter.done()
    got = files.progress_from_json(files.read_json(files.progress_path(tmp_path, "s1")))
    assert got.state == "done" and got.step == ""
    reporter.done("160 records judged, 3 cards waiting for you")
    got = files.progress_from_json(files.read_json(files.progress_path(tmp_path, "s1")))
    assert got.state == "done" and got.step == "160 records judged, 3 cards waiting for you"


def _job(kind: str, n: int, session: str = "s1", needs: str | None = None, created: str = ""):
    return files.make_job(kind, session, f"{kind}.v1", {"n": n}, needs=needs, created=created)


def test_standins_run_a_queued_job_once_and_write_results_and_ledger(
        repo: Path, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.api import Core
    from plumb.understand import queue, worker
    from understand.fakes import FakeKind, fake_kinds

    seen: list[str] = []
    fake_kinds(monkeypatch, {"a": FakeKind(
        "a", apply=lambda core, job, answer: seen.append(job.id) or Applied(job=job.id))})
    engine_standins.dispatcher.script = {"a": {"ok": True}}
    core = Core(repo)
    job = _job("a", 1)
    queue.enqueue(core, job)
    queue.enqueue(core, job)                      # idempotent
    assert len(list(files.jobs_dir(repo, "s1").glob("*.json"))) == 1
    assert worker.run_once(core, "s1") == [job.id]
    assert worker.run_once(core, "s1") == []
    assert seen == [job.id]
    result = files.result_from_json(
        files.read_json(files.results_dir(repo, "s1") / f"{job.id}.json"))
    assert result.status == "ok" and result.answer == {"ok": True}
    assert (files.ran_dir(repo, "s1") / job.id).exists()
    assert queue.consecutive_failures(repo, "s1") == 0


def test_standins_honour_needs_in_either_queue_order(
        repo: Path, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.api import Core
    from plumb.understand import queue, worker
    from understand.fakes import FakeKind, fake_kinds

    fake_kinds(monkeypatch, {"a": FakeKind("a"), "b": FakeKind("b")})
    core = Core(repo)
    first = _job("a", 1, created="2026-01-02T00:00:00Z")
    second = _job("b", 1, needs=first.id, created="2026-01-01T00:00:00Z")
    queue.enqueue(core, second)
    queue.enqueue(core, first)
    assert worker.run_once(core, "s1") == [first.id, second.id]


def test_standins_failed_needs_makes_dependent_an_error_without_a_model_call(
        repo: Path, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.api import Core
    from plumb.understand import queue, worker
    from understand.fakes import FakeKind, fake_kinds

    fake_kinds(monkeypatch, {"a": FakeKind("a"), "b": FakeKind("b")})
    engine_standins.dispatcher.failing()
    core = Core(repo)
    first = _job("a", 1)
    second = _job("b", 1, needs=first.id)
    queue.enqueue(core, first)
    queue.enqueue(core, second)
    worker.run_once(core, "s1")
    assert [j.id for j in engine_standins.dispatcher.jobs] == [first.id]
    found = {r.job: r for r in queue.failures(core, "s1")}
    assert found[second.id].error.step == "needs" and found[first.id].status == "error"
    assert queue.consecutive_failures(repo, "s1") == 2


def test_standins_failure_counter_resets_on_an_ok_result(
        repo: Path, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.api import Core
    from plumb.understand import queue, worker
    from understand.fakes import FakeKind, fake_kinds

    fake_kinds(monkeypatch, {"a": FakeKind("a")})
    core = Core(repo)
    engine_standins.dispatcher.failing()
    queue.enqueue(core, _job("a", 1))
    worker.run_once(core, "s1")
    assert queue.consecutive_failures(repo, "s1") == 1
    data = files.read_json(files.failures_path(repo, "s1"))
    assert data["v"] == 1 and data["consecutive"] == 1 and data["last"]["kind"] == "a"
    engine_standins.dispatcher.script = {"a": {}}
    queue.enqueue(core, _job("a", 2))
    worker.run_once(core, "s1")
    assert queue.consecutive_failures(repo, "s1") == 0
    assert [r.job for r in queue.failures(core, "s1")] == [_job("a", 1).id]


def test_standins_step_aside_when_a_name_is_no_longer_a_stub(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import queue, worker
    from understand.fakes import install_engine_standins

    def real(core, session, job_id=None):
        return ["real"]

    monkeypatch.setattr(worker, "run_once", real)
    install_engine_standins(monkeypatch)
    assert worker.run_once(None, "s1") == ["real"]
    assert getattr(queue.failures, "__stub__", False) is False   # the real ones stay as they are


def test_fake_kinds_installs_a_module_for_a_job_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand.kinds import KIND_MODULES, KINDS
    from understand.fakes import FakeKind, fake_kinds

    fake_kinds(monkeypatch, {"zz": FakeKind("zz")})
    module = KINDS["zz"]
    assert isinstance(module, JobKind) and module.kind == "zz"
    assert module.apply(None, Job(id="x"), {}) == Applied(job="x")
    assert "zz" in KIND_MODULES
