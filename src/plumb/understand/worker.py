"""The worker (ENGINE): runs the queued jobs of one session, one worker per session.

It knows nothing about what a read, a judgment or a clarification means. For each job it asks
the kind to ``recompute`` the inputs from the logs (the queued file is never trusted), asks
the one configured dispatcher, checks the answer against the kind's schema, lets the kind
``apply`` it in memory and writes what that changed, then the result and the ledger entry.
A result is a record of what happened and is never read to apply anything.

The worker makes the token of ``worker.lock`` and holds it in its own environment as
``PLUMB_WORKER`` while it applies; the dispatcher's child process never gets it."""

from __future__ import annotations

import calendar
import contextlib
import dataclasses
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, DispatchError, Job, JobError, JobResult, NoModel
from plumb.understand import agents, dispatch, files, jobs, ledger
from plumb.understand import schema as schema_check

STALE_S = 30.0                  # a lock whose heartbeat is older is taken over
HEARTBEAT_S = 5.0
MIDWAY_S = 120.0     # a count older than this is not the pass in progress
_HELD: dict[tuple[str, str], str] = {}     # the locks this process holds: (root, session) -> token


# ---- the lock -------------------------------------------------------------------------------

def budget_scale_for(root: Path, session: str) -> int:
    """SR-325 EX-5, DEC-260: one more than the failures in a row, so each retry of a failed
    job gets a larger budget than the last (the dispatcher's timeout is scaled by it)."""
    from plumb.understand import queue

    return 1 + queue.consecutive_failures(root, session)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32           # type: ignore[attr-defined]
        handle = kernel.OpenProcess(0x1000, False, pid)    # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5 or kernel.GetLastError() == 5   # access denied
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and \
                code.value == 259                 # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _key(root: Path, session: str) -> tuple[str, str]:
    return (str(Path(root).resolve()), session)


def _lock_is_held(root: Path, session: str, path: Path) -> bool:
    """True when the lock on disk belongs to a worker that is alive and recently heard from."""
    raw = files.read_json(path)
    if not isinstance(raw, Mapping):
        try:
            return time.time() - path.stat().st_mtime < 5.0     # being written right now
        except OSError:
            return False
    try:
        pid, beat = int(raw.get("pid") or 0), float(raw.get("heartbeat") or 0)
    except (TypeError, ValueError):
        return False
    if pid == os.getpid() and _key(root, session) not in _HELD:
        return False                              # ours from an earlier run that never let go
    return time.time() - beat < STALE_S and _pid_alive(pid)


def acquire(root: Path, session: str) -> str | None:
    """Take the session's worker lock: its new token, or None when a live worker holds it. A
    stale lock (its process gone, or silent for ``STALE_S``) is taken over."""
    root = Path(root)
    key = _key(root, session)
    if key in _HELD:
        return None
    path = files.lock_path(root, session)
    token = secrets.token_hex(16)
    body = json.dumps({"pid": os.getpid(), "heartbeat": time.time(), "token": token})
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_held(root, session, path):
                return None
            try:
                path.unlink()
            except OSError:
                return None
            continue
        except OSError:
            return None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        _HELD[key] = token
        return token
    return None


def heartbeat(root: Path, session: str, token: str) -> None:
    try:
        files.write_json_atomic(files.lock_path(root, session), {
            "pid": os.getpid(), "heartbeat": time.time(), "token": token})
    except OSError:
        pass                                      # a missed beat is made up by the next one


def release(root: Path, session: str, token: str) -> None:
    _HELD.pop(_key(Path(root), session), None)
    path = files.lock_path(Path(root), session)
    raw = files.read_json(path)
    if isinstance(raw, Mapping) and raw.get("token") == token:
        with contextlib.suppress(OSError):
            path.unlink()


@contextlib.contextmanager
def _as_worker(token: str) -> Iterator[None]:
    old = os.environ.get("PLUMB_WORKER")
    os.environ["PLUMB_WORKER"] = token
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("PLUMB_WORKER", None)
        else:
            os.environ["PLUMB_WORKER"] = old


# ---- starting one ---------------------------------------------------------------------------

def start_detached(root: Path, session: str) -> None:
    """Ask for a worker for ``session``: a detached process, unless a live one has the lock.
    Never waits and never raises (a hook calls this)."""
    root = Path(root)
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("PLUMB_FAKE_DISPATCH"):
        return None          # a test that queues a job does not start a process of its own
    try:
        path = files.lock_path(root, session)
        if path.exists() and _lock_is_held(root, session, path):
            return None
        from plumb.background import popen_options

        options = popen_options(root)   # no console window for it or what it runs
        env ={k: v for k, v in os.environ.items() if k not in ("PLUMB_WORKER", "PLUMB_JOB")}
        subprocess.Popen([sys.executable, "-m", "plumb", "understand", "worker", "--session",
                          session, "--root", str(root)], env=env, **options)
    except OSError:
        return None
    return None


# ---- running jobs ---------------------------------------------------------------------------

def say(root: Path, session: str, line: str) -> None:
    """A once-per-window line for the agent: it waits in the session's notes for the next
    prompt hook (``prompt.agent_notes``), as the stop hook's warnings do."""
    path = files.session_dir(Path(root), session) / "agent_notes.json"
    notes = files.read_json(path)
    with contextlib.suppress(OSError):
        files.write_json_atomic(path, [*(notes if isinstance(notes, list) else []), line])


def _note(core: Any, kind: str, job: str, detail: str) -> None:
    core.log_append("events", "job-note", {"kind": kind, "job": job, "detail": detail})


def _noted(core: Any, job: str, detail_part: str) -> bool:
    from plumb import log

    return any(e.payload.get("job") == job and detail_part in str(e.payload.get("detail", ""))
               for e in log.read(core.paths, "events", ["job-note"]))


def _write_applied(core: Any, session: str, applied: Applied) -> None:
    """What applying changed, written by the worker: cards, then log entries, then notes."""
    from itertools import groupby

    from plumb import log
    from plumb.understand import cardstore

    if applied.cards or applied.closed:
        replaced = {c.id for c in applied.cards}
        kept = [dataclasses.replace(c, status="closed") if c.id in applied.closed else c
                for c in cardstore.own_cards(core.root, session) if c.id not in replaced]
        cardstore.save(core.root, session, [*kept, *applied.cards])
    for stream, group in groupby(applied.entries, key=lambda e: log.stream_of(str(e["kind"]))):
        core.log_append_many(stream, [(str(e["kind"]), dict(e["payload"])) for e in group])
    for text in applied.notes:
        _note(core, "worker", applied.job, text)


FAILED_STEP = "{step} did not finish"


class _Ticker:
    """Says the step again every ``interval`` seconds while a model call is out, and keeps the
    lock's heartbeat fresh."""

    def __init__(self, pass_: _Pass, reporter: Any, step: str, interval: float,
                 counts: tuple[int, int] = (0, 0)) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, args=(
            pass_, reporter, step, max(0.05, interval), counts))

    def _loop(self, pass_: _Pass, reporter: Any, step: str, interval: float,
              counts: tuple[int, int]) -> None:
        last_beat = time.monotonic()
        while not self._stop.wait(interval):
            try:
                reporter.update(step, *counts)
                if time.monotonic() - last_beat >= HEARTBEAT_S:
                    heartbeat(pass_.root, pass_.session, pass_.token)
                    last_beat = time.monotonic()
            except Exception:  # noqa: BLE001 - a missed tick is made up by the next one
                pass

    def __enter__(self) -> _Ticker:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(5)


class _Pass:
    """One pass over a session's queue (the worker holds the lock)."""

    def __init__(self, core: Any, session: str, token: str) -> None:
        self.core = core
        self.root = Path(core.root)
        self.session = session
        self.token = token
        self.seen: set[str] = set()
        self.ran: list[str] = []
        self.queued: dict[str, Job] = {}

    # -- bookkeeping the owner never sees
    def report_unledgered(self) -> None:
        for job_id in ledger.unledgered(self.root, self.session):
            if not _noted(self.core, job_id, "ledger"):
                _note(self.core, "worker", job_id,
                      "a result is there that the worker did not write (no ledger entry); "
                      "it confirms nothing and the job is run again")

    def _count(self, job: Job, result: JobResult) -> None:
        """``failures.json``: up by one on an error result, back to 0 on an ok one."""
        path = files.failures_path(self.root, self.session)
        data = files.read_json(path)
        data = data if isinstance(data, Mapping) else {}
        if result.status == "ok":
            new = {"v": 1, "consecutive": 0, "last": data.get("last")}
        else:
            new = {"v": 1, "consecutive": int(data.get("consecutive") or 0) + 1,
                   "last": {"job": job.id, "kind": job.kind,
                            "step": result.error.step if result.error else "",
                            "at": jobs.now()}}
        files.write_json_atomic(path, new)
        if new["consecutive"] == 3:  # SR-325 EX-5: the third failure in a row is one case
            from plumb import debug

            debug.open_case(self.root, id=f"job-{job.id}", kind="job-failed", target=job.id,
                            detail=f"{job.kind} failed three times in a row, each retry with "
                                   "a larger budget",
                            log=json.dumps(new["last"]))

    def _finish(self, job: Job, result: JobResult) -> None:
        ledger.record(self.root, self.session, job.id)
        jobs.write_result(self.root, self.session, result)
        self._count(job, result)
        self.ran.append(job.id)

    def _step_text(self, job: Job) -> str:
        from plumb.understand.kinds import KINDS

        try:
            return str(KINDS[job.kind].describe(job))
        except Exception:  # noqa: BLE001 - a kind with no words says its name
            return job.kind

    def _progress(self, job: Job) -> Any:
        from plumb.progress import Reporter

        return Reporter(self.root, self.session, job.kind)

    def _error(self, job: Job, step: str, message: str, started: str, t0: float,
               dispatcher: str = "") -> None:
        try:
            self._progress(job).failed(FAILED_STEP.format(step=self._step_text(job)))
        except Exception:  # noqa: BLE001 - the line is a courtesy
            pass
        self._finish(job, JobResult(
            job=job.id, status="error", error=JobError(step, message), dispatcher=dispatcher,
            started=started, finished=jobs.now(), run_s=round(time.perf_counter() - t0, 3)))

    # -- order
    def process(self, job: Job) -> None:
        if job.id in self.seen or jobs.result(self.root, self.session, job.id) is not None:
            return
        self.seen.add(job.id)
        started, t0 = jobs.now(), time.perf_counter()
        if job.needs:
            need = jobs.result(self.root, self.session, job.needs)
            if need is None and job.needs in self.queued:
                self.process(self.queued[job.needs])
                need = jobs.result(self.root, self.session, job.needs)
            if need is None and job.needs not in self.queued:
                _note(self.core, job.kind, job.id,
                      f"it needs {job.needs}, which has no job file and no result; "
                      "treated as satisfied")
            elif need is None or need.status != "ok":
                self._error(job, "needs", "the job it waits for did not end well", started, t0)
                return
        self.execute(job, started, t0)

    # -- one job
    def execute(self, job: Job, started: str, t0: float) -> None:
        from plumb.understand.kinds import KINDS

        try:
            module = KINDS[job.kind]
        except (KeyError, ImportError) as exc:
            self._error(job, "kind", f"no job kind {job.kind!r} ({exc})", started, t0)
            return
        reporter = self._progress(job)
        step = self._step_text(job)
        counts = self._carried(reporter)
        with contextlib.suppress(Exception):
            reporter.update(step, *counts)
        try:
            recomputed = module.recompute(self.core, job)
        except Exception as exc:  # noqa: BLE001 - a kind that fails is an error result
            self._error(job, "inputs", f"{type(exc).__name__}: {exc}", started, t0)
            return
        if recomputed is None:
            self._clear(reporter)
            _note(self.core, job.kind, job.id, "nothing left to check; no model was asked")
            self._finish(job, JobResult(job=job.id, status="ok", started=started,
                                        finished=jobs.now(),
                                        run_s=round(time.perf_counter() - t0, 3)))
            return
        if files.canonical(recomputed) != files.canonical(job.inputs):
            _note(self.core, job.kind, job.id,
                  "the inputs in the job file differ from the ones recomputed from the logs; "
                  "the recomputed ones are used")
            job = dataclasses.replace(job, inputs=dict(recomputed),
                                      inputs_digest=files.digest_of(recomputed))
        step = self._step_text(job)
        with contextlib.suppress(Exception):
            reporter.update(step, *counts)
        got = self._ask(module, job, reporter, step, counts, started, t0)
        if got is None:
            return
        answer, dname, left = got
        found = schema_check.problems(answer, module.schema)
        if found:
            self._error(job, "schema", "; ".join(found[:3]), started, t0, dname)
            return
        try:
            with _as_worker(self.token):
                _write_applied(self.core, self.session,
                               module.apply(self.core, job, dict(answer)))
            if left:
                self._hold(job, left)
        except Exception as exc:  # noqa: BLE001 - the kind or the log refused
            self._error(job, "apply", f"{type(exc).__name__}: {exc}", started, t0,
                        dname)
            return
        self._clear(reporter)
        self._finish(job, JobResult(
            job=job.id, status="ok", answer=dict(answer), dispatcher=dname,
            started=started, finished=jobs.now(), run_s=round(time.perf_counter() - t0, 3)))

    def _hold(self, job: Job, left: Any) -> None:
        """SR-185: the records nobody could judge stay a job of their own, for the next run."""
        again = files.make_job(job.kind, job.session, job.schema,
                               {**job.inputs, "records": list(left)}, needs=job.needs,
                               created=jobs.now())
        files.write_json_atomic(jobs.job_path(self.root, job.session, again.id),
                                files.job_to_json(again))

    def _say(self, line: str) -> None:
        say(self.root, self.session, line)

    def _ask(self, module: Any, job: Job, reporter: Any, step: str, counts: tuple[int, int],
             started: str, t0: float
             ) -> tuple[dict[str, Any], str, tuple[Any, ...]] | None:
        """The kind's answer, who gave it and the records it left, or None after the job's error was written."""
        cascade = getattr(module, "cascade", None)
        if cascade is not None:             # SR-182: the kind chooses who answers
            try:
                with _Ticker(self, reporter, step, float(getattr(
                        self.core.config.understand, "progress_interval_s", 1) or 1), counts):
                    done = cascade(self.core, job, system=agents.load(job.kind),
                                   schema=module.schema)
            except module.Waiting as wait:
                if wait.line:
                    self._say(wait.line)
                self._error(job, "dispatch", str(wait.cause), started, t0)
                return None
            except DispatchError as exc:
                self._error(job, exc.step, exc.message, started, t0)
                return None
            except Exception as exc:  # noqa: BLE001 - any failure of a judge is the job's
                self._error(job, "run", f"{type(exc).__name__}: {exc}", started, t0)
                return None
            if done.line:
                self._say(done.line)
            return done.answer, done.dispatcher, done.left
        scale = dispatch.budget_scale.set(budget_scale_for(self.root, self.session))
        try:
            dispatcher = dispatch.configured(self.core)
        except NoModel as exc:
            self._error(job, "dispatch", str(exc), started, t0)
            return None
        finally:
            dispatch.budget_scale.reset(scale)
        reason = dispatcher.available()
        if reason:
            self._error(job, "dispatch", reason, started, t0, dispatcher.name)
            return None
        interval = float(getattr(self.core.config.understand, "progress_interval_s", 1) or 1)
        try:
            with _Ticker(self, reporter, step, interval, counts):
                answer = dispatcher.run(
                    job, system=agents.load(job.kind),
                    user=json.dumps(job.inputs, ensure_ascii=False, sort_keys=True, indent=1),
                    schema=module.schema, on_step=lambda text: None)
        except DispatchError as exc:
            self._error(job, exc.step, exc.message, started, t0, dispatcher.name)
            return None
        except Exception as exc:  # noqa: BLE001 - any failure of a dispatcher is the job's
            self._error(job, "run", f"{type(exc).__name__}: {exc}", started, t0,
                        dispatcher.name)
            return None
        return dict(answer), dispatcher.name, ()

    def _carried(self, reporter: Any) -> tuple[int, int]:
        """The count a pass of many jobs (the backlog) left on the line a moment ago, so the
        next job goes on from it instead of starting the count again."""
        shown = files.progress_from_json(files.read_json(reporter.path))
        if shown is None or not self._midway(shown, reporter.kind):
            return 0, 0
        return shown.done, shown.total

    @staticmethod
    def _midway(shown: Any, kind: str) -> bool:
        if shown.state != "running" or shown.kind != kind or not 0 <= shown.done < shown.total:
            return False
        try:
            age = time.time() - calendar.timegm(time.strptime(shown.updated, "%Y-%m-%dT%H:%M:%SZ"))
        except (TypeError, ValueError):
            return False
        return age < MIDWAY_S

    def _clear(self, reporter: Any) -> None:
        """The line goes when the job ends, unless the job's own ``apply`` left an end line
        (state done, words in the step) or a count of a pass with more jobs to run: those are
        for the status line to show."""
        shown = files.progress_from_json(files.read_json(reporter.path))
        if shown is not None and shown.state == "done" and shown.step:
            return
        if shown is not None and self._midway(shown, reporter.kind):
            return
        with contextlib.suppress(OSError):
            reporter.path.unlink()

    def run(self, job_id: str | None) -> list[str]:
        self.report_unledgered()
        self.queued = {j.id: j for j in jobs.queued(self.root, self.session)}
        if job_id is not None:
            for job in [self.queued[job_id]] if job_id in self.queued else []:
                self.process(job)
            return self.ran
        # the queue is read again before each job: an answer queued meanwhile goes before the
        # backlog pass's remaining jobs (jobs.queued sorts those last)
        seen: set[str] = set()
        while (job := next((j for j in jobs.queued(self.root, self.session)
                            if j.id not in seen), None)) is not None:
            seen.add(job.id)
            self.queued[job.id] = job
            self.process(job)
        return self.ran


def _run_locked(core: Any, session: str, token: str, job_id: str | None) -> list[str]:
    return _Pass(core, session, token).run(job_id)


def run_once(core: Any, session: str, job_id: str | None = None) -> list[str]:
    """Run the queued jobs of the session in the worker's order (or the one job given and its
    ``needs``); the ids run. Nothing runs when another live worker holds the session."""
    if core is None:
        return []
    root = Path(core.root)
    token = acquire(root, session)
    if token is None:
        return []
    try:
        return _run_locked(core, session, token, job_id)
    finally:
        release(root, session, token)


def run_loop(core: Any, session: str) -> None:
    """Run jobs until none is left (the worker's loop). The lock is let go before the last look
    at the queue, so a job queued as the worker leaves starts a worker of its own."""
    if core is None:
        return None
    root = Path(core.root)
    from plumb.understand.summary import after_stop

    try:
        after_stop(core, session)   # SR-375: what the last turn end left for the background
    except Exception:  # noqa: BLE001 - the jobs still run
        pass
    idle_looks = 0
    while True:
        token = acquire(root, session)
        if token is None:
            return None
        try:
            ran = _run_locked(core, session, token, None)
        finally:
            release(root, session, token)
        if ran:
            idle_looks = 0
        elif not jobs.pending(root, session) or idle_looks >= 3:
            return None
        else:
            idle_looks += 1
            time.sleep(0.2)
