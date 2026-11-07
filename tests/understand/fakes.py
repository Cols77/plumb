"""Fakes of the understanding layer (docs/plans/sp8-plan.md 3.2 item 9).

``FakeDispatcher(script)``: answers by job kind (a mapping) or through a callable, records
every job, can block on an event or raise ``DispatchError``. ``as_worker(root, session)``: a
context manager that writes a ``worker.lock`` with a token and sets ``PLUMB_WORKER``, for
tests that apply a kind in process. ``fake_claude``: a stand-in ``claude`` executable that
records its argv, working directory, environment and stdin.

Phase C2 (plan 3.2a): ``engine_standins`` (fixture) replaces the queue and worker stubs with an
in-process implementation of the same contract until ENGINE's code is on main (a name that is
no longer a ``@stub`` is left alone); ``fake_kinds`` installs test-only job kinds;
``owner_level(text)`` returns the offences of both owner-text scanners.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import secrets
import stat
import sys
import threading
import time
import types
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from plumb.contracts import (
    Applied,
    DispatchError,
    Job,
    JobError,
    JobResult,
)

Script = Mapping[str, Any] | Callable[[Job], Mapping[str, Any]]


@dataclass
class FakeDispatcher:
    """A ``Dispatcher`` whose answers the test scripts.

    ``script``: ``{kind: answer}`` where an answer is a mapping, an exception (raised), or a
    callable taking the job; or one callable for every kind. ``block``: an event the run waits
    for before answering (``blocked`` is set once a run has started waiting)."""

    script: Script = field(default_factory=dict)
    name: str = "fake"
    reason: str | None = None            # a plain reason when not available
    block: threading.Event | None = None
    jobs: list[Job] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    blocked: threading.Event = field(default_factory=threading.Event)

    def available(self) -> str | None:
        return self.reason

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Callable[[str], None]) -> Mapping[str, Any]:
        self.jobs.append(job)
        self.calls.append({"job": job.id, "kind": job.kind, "system": system, "user": user,
                           "schema": dict(schema)})
        on_step(f"running {job.kind}")
        if self.block is not None:
            self.blocked.set()
            self.block.wait(10)
        answer = self.script(job) if callable(self.script) else self.script.get(job.kind, {})
        if callable(answer):
            answer = answer(job)
        if isinstance(answer, BaseException):
            raise answer
        return dict(answer)

    def failing(self, step: str = "run", message: str = "the model could not be reached"
                ) -> FakeDispatcher:
        self.script = lambda job: DispatchError(step, message)   # every kind, fake ones too
        return self

    def ran(self, kind: str | None = None) -> list[Job]:
        return [j for j in self.jobs if kind in (None, j.kind)]


@contextlib.contextmanager
def as_worker(root: Path, session: str) -> Iterator[str]:
    """Write ``.plumb/session/<session>/worker.lock`` with a fresh token and set
    ``PLUMB_WORKER`` to it, for the block; yields the token."""
    token = secrets.token_hex(16)
    lock = Path(root) / ".plumb" / "session" / session / "worker.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "heartbeat": time.time(), "token": token}),
                    encoding="utf-8")
    old = os.environ.get("PLUMB_WORKER")
    os.environ["PLUMB_WORKER"] = token
    try:
        yield token
    finally:
        if old is None:
            os.environ.pop("PLUMB_WORKER", None)
        else:
            os.environ["PLUMB_WORKER"] = old


_FAKE_CLAUDE = '''\
import json, os, sys
record = {"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ),
          "stdin": sys.stdin.read()}
with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
sys.stdout.write(os.environ.get("FAKE_CLAUDE_ANSWER", "{}"))
'''


@dataclass
class FakeClaude:
    """A stand-in ``claude`` executable on a directory the test puts on ``PATH``."""

    directory: Path
    log: Path
    answer: str = "{}"

    @property
    def path(self) -> Path:
        return self.directory / ("claude.cmd" if sys.platform == "win32" else "claude")

    def env(self, base: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ if base is None else base)
        env["PATH"] = f"{self.directory}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_CLAUDE_LOG"] = str(self.log)
        env["FAKE_CLAUDE_ANSWER"] = self.answer
        return env

    def calls(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()
                if line.strip()]


def fake_claude(directory: Path, answer: Mapping[str, Any] | str = "{}") -> FakeClaude:
    """Create the fake ``claude`` in ``directory``; every call is recorded in ``claude.log``
    (argv, cwd, environment, stdin) and answers with ``answer``."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "fake_claude.py"
    script.write_text(_FAKE_CLAUDE, encoding="utf-8")
    fake = FakeClaude(directory, directory / "claude.log",
                      answer if isinstance(answer, str) else json.dumps(answer))
    if sys.platform == "win32":
        fake.path.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        fake.path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
                             encoding="utf-8")
        fake.path.chmod(fake.path.stat().st_mode | stat.S_IEXEC)
    return fake


# ---- phase C2: owner-level scan, fake kinds, ENGINE stand-ins --------------------------------

_INTERNAL_WORDS = re.compile(r"\b(jobs?|dispatchers?|hash(?:es)?|workers?)\b", re.IGNORECASE)
_BARE_ID = re.compile(r"(?<![\w-])(?:(?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![\w-])")


def owner_level(text: str) -> list[str]:
    """The offences of both owner-text scanners on ``text``: bare ``plumb <verb>`` commands
    (``bare_cli_verbs``), then plumb internals ("job", "dispatcher", "hash", "worker") and bare
    record IDs. An empty list means the text is at the owner's level."""
    from plumb.present.owner_text import bare_cli_verbs

    return [*bare_cli_verbs(text), *(m.group(0) for m in _INTERNAL_WORDS.finditer(text)),
            *(m.group(0) for m in _BARE_ID.finditer(text))]


@dataclass
class FakeKind:
    """A test-only ``JobKind``; every method has a harmless default."""

    kind: str
    schema: Mapping[str, Any] = field(default_factory=dict)
    build: Callable[..., Job | None] | None = None
    recompute: Callable[[Any, Job], Mapping[str, Any] | None] | None = None
    apply: Callable[[Any, Job, Mapping[str, Any]], Applied] | None = None
    describe: Callable[[Job], str] | None = None

    def module(self) -> types.ModuleType:
        module = types.ModuleType(f"plumb_test_kind_{self.kind}")
        module.kind = self.kind  # type: ignore[attr-defined]
        module.schema = dict(self.schema)  # type: ignore[attr-defined]
        module.build = self.build or (  # type: ignore[attr-defined]
            lambda core, session, **context: None)
        module.recompute = self.recompute or (  # type: ignore[attr-defined]
            lambda core, job: dict(job.inputs))
        module.apply = self.apply or (  # type: ignore[attr-defined]
            lambda core, job, answer: Applied(job=job.id))
        module.describe = self.describe or (lambda job: self.kind)  # type: ignore[attr-defined]
        return module


def fake_kinds(monkeypatch: pytest.MonkeyPatch, kinds: Mapping[str, FakeKind]) -> None:
    """Install a module per fake kind in ``sys.modules`` and ``kinds.KIND_MODULES`` (undone
    with the test)."""
    from plumb.understand import kinds as registry

    for name, fake in kinds.items():
        module = fake.module()
        monkeypatch.setitem(sys.modules, module.__name__, module)
        monkeypatch.setitem(registry.KIND_MODULES, name, module.__name__)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class EngineStandins:
    dispatcher: FakeDispatcher = field(default_factory=FakeDispatcher)


def _standin_functions(box: EngineStandins) -> dict[tuple[str, str], Callable[..., Any]]:
    from plumb.log import append, stream_of
    from plumb.understand import files
    from plumb.understand.kinds import KINDS

    def enqueue(core: Any, job: Job) -> None:
        path = files.jobs_dir(core.root, job.session) / f"{job.id}.json"
        if path.exists():
            return
        files.write_json_atomic(path, files.job_to_json(
            dataclasses.replace(job, created=job.created or _now())))

    def read_result(core: Any, session: str, job_id: str) -> JobResult | None:
        raw = files.read_json(files.results_dir(core.root, session) / f"{job_id}.json")
        return files.result_from_json(raw) if isinstance(raw, Mapping) else None

    def count(core: Any, session: str, result: JobResult, job: Job) -> None:
        path = files.failures_path(core.root, session)
        data = files.read_json(path) or {}
        if result.status == "ok":
            new = {"v": 1, "consecutive": 0, "last": data.get("last")}
        else:
            new = {"v": 1, "consecutive": int(data.get("consecutive") or 0) + 1,
                   "last": {"job": job.id, "kind": job.kind,
                            "step": result.error.step if result.error else "", "at": _now()}}
        files.write_json_atomic(path, new)

    def finish(core: Any, session: str, job: Job, result: JobResult) -> None:
        files.write_json_atomic(files.results_dir(core.root, session) / f"{job.id}.json",
                                files.result_to_json(result))
        ran = files.ran_dir(core.root, session) / job.id
        ran.parent.mkdir(parents=True, exist_ok=True)
        ran.write_text(f"{os.getpid()} {_now()}\n", encoding="utf-8")
        count(core, session, result, job)

    def error(job: Job, step: str, message: str, started: str) -> JobResult:
        return JobResult(job=job.id, status="error", error=JobError(step, message),
                         dispatcher=box.dispatcher.name, started=started, finished=_now())

    def write_applied(core: Any, session: str, applied: Applied) -> None:
        for entry in applied.entries:
            kind = str(entry["kind"])
            append(core.paths, stream_of(kind), kind, dict(entry["payload"]))

    def run_job(core: Any, session: str, job: Job) -> None:
        started = _now()
        if job.needs:
            need = read_result(core, session, job.needs)
            if need is not None and need.status != "ok":
                finish(core, session, job, error(job, "needs", "the job it needs failed",
                                                 started))
                return
        module = KINDS[job.kind]
        try:
            recomputed = module.recompute(core, job)
            if recomputed is not None:
                job = dataclasses.replace(job, inputs=dict(recomputed))
            with as_worker(core.root, session):
                answer = box.dispatcher.run(job, system="", user=json.dumps(job.inputs),
                                            schema=module.schema, on_step=lambda step: None)
                write_applied(core, session, module.apply(core, job, answer))
        except DispatchError as exc:
            finish(core, session, job, error(job, getattr(exc, "step", "run"), str(exc),
                                             started))
            return
        except Exception as exc:  # noqa: BLE001 - a stand-in reports any failure as a result
            finish(core, session, job, error(job, "apply", f"{type(exc).__name__}: {exc}",
                                             started))
            return
        finish(core, session, job, JobResult(
            job=job.id, status="ok", answer=dict(answer), dispatcher=box.dispatcher.name,
            started=started, finished=_now()))

    def run_once(core: Any, session: str, job_id: str | None = None) -> list[str]:
        queued: dict[str, Job] = {}
        for path in files.jobs_dir(core.root, session).glob("*.json"):
            raw = files.read_json(path)
            if isinstance(raw, Mapping):
                job = files.job_from_json(raw)
                queued[job.id] = job
        ran: list[str] = []

        def run(job: Job) -> None:
            if job.id in ran or read_result(core, session, job.id) is not None:
                return
            if job.needs and job.needs in queued:
                run(queued[job.needs])
            run_job(core, session, job)
            ran.append(job.id)

        wanted = [queued[job_id]] if job_id in queued else (
            [] if job_id else sorted(queued.values(), key=lambda j: (j.created, j.id)))
        for job in wanted:
            run(job)
        return ran

    def run_loop(core: Any, session: str) -> None:
        run_once(core, session)

    def failures(core: Any, session: str) -> list[JobResult]:
        found = [r for p in files.results_dir(core.root, session).glob("*.json")
                 if (r := read_result(core, session, p.stem)) is not None]
        return sorted((r for r in found if r.status == "error"),
                      key=lambda r: (r.started, r.job))

    def consecutive_failures(root: Any, session: str) -> int:
        data = files.read_json(files.failures_path(Path(root), session))
        return int(data.get("consecutive") or 0) if isinstance(data, Mapping) else 0

    return {("queue", "enqueue"): enqueue, ("worker", "run_once"): run_once,
            ("worker", "run_loop"): run_loop, ("queue", "failures"): failures,
            ("queue", "consecutive_failures"): consecutive_failures}


def install_engine_standins(monkeypatch: pytest.MonkeyPatch,
                            dispatcher: FakeDispatcher | None = None) -> EngineStandins:
    """Replace ``queue.enqueue``, ``worker.run_once``, ``worker.run_loop``, ``queue.failures``
    and ``queue.consecutive_failures`` by in-process versions of the same contract. A name whose
    real code has landed (no ``__stub__``) is left alone; ``enqueue`` carries no marker, so it
    is replaced while ``worker.run_once`` is still a stub (ENGINE lands them together)."""
    from plumb.understand import queue, worker

    box = EngineStandins(dispatcher or FakeDispatcher())
    modules = {"queue": queue, "worker": worker}
    engine_landed = not getattr(worker.run_once, "__stub__", False)
    if engine_landed:
        # the real worker runs; it only gets the fake model (the one configured dispatcher)
        from plumb.understand import dispatch

        monkeypatch.setattr(dispatch, "configured", lambda core, model=None: box.dispatcher)
    for (module_name, name), func in _standin_functions(box).items():
        module = modules[module_name]
        if name == "enqueue":
            if engine_landed:
                continue
        elif not getattr(getattr(module, name), "__stub__", False):
            continue
        func.__stub__ = False  # type: ignore[attr-defined]
        monkeypatch.setattr(module, name, func)
    return box


@pytest.fixture
def engine_standins(monkeypatch: pytest.MonkeyPatch) -> EngineStandins:
    return install_engine_standins(monkeypatch)
