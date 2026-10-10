"""Fakes of the understanding layer (docs/plans/sp8-plan.md 3.2 item 9).

``FakeDispatcher(script)``: answers by job kind (a mapping) or through a callable, records
every job, can block on an event or raise ``DispatchError``. ``as_worker(root, session)``: a
context manager that writes a ``worker.lock`` with a token and sets ``PLUMB_WORKER``, for
tests that apply a kind in process. ``fake_claude``: a stand-in ``claude`` executable that
records its argv, working directory, environment and stdin.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import DispatchError, Job

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
        self.script = {k: DispatchError(step, message) for k in ("read", "judge", "clarify")}
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
