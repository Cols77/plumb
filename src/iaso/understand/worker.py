"""The worker (ENGINE): runs the queued jobs of one session, one worker per session.

It knows nothing about what a read, a judgment or a clarification means. For each job it asks
the kind to ``recompute`` the inputs from the logs (the queued file is never trusted), asks
the one configured dispatcher, checks the answer against the kind's schema, lets the kind
``apply`` it in memory and writes what that changed, then the result and the ledger entry.
A result is a record of what happened and is never read to apply anything.

The worker makes the token of ``worker.lock`` and holds it in its own environment as
``IASO_WORKER`` while it applies; the dispatcher's child process never gets it."""

from __future__ import annotations

import calendar
import concurrent.futures
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

from iaso.contracts import Applied, DispatchError, Job, JobError, JobResult, NoModel
from iaso.understand import agents, dispatch, files, jobs, ledger
from iaso.understand import schema as schema_check

STALE_S = 30.0                  # a lock whose heartbeat is older is taken over
HEARTBEAT_S = 5.0
MIDWAY_S = 120.0     # a count older than this is not the pass in progress
_HELD: dict[tuple[str, str], str] = {}     # the locks this process holds: (root, session) -> token


# ---- the lock -------------------------------------------------------------------------------

def budget_scale_for(root: Path, session: str) -> int:
    """SR-325 EX-5, DEC-260: one more than the failures in a row, so each retry of a failed
    job gets a larger budget than the last (the dispatcher's timeout is scaled by it)."""
    from iaso.understand import queue

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
def _beating(root: Path, session: str, token: str) -> Iterator[None]:
    """Keep the held lock's heartbeat fresh for as long as the work inside takes: a step with no
    model call out (the turn's upkeep, a recompute over the whole log) can outlast ``STALE_S``,
    and a silent lock is taken over by a second worker while the first still runs."""
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(HEARTBEAT_S):
            heartbeat(root, session, token)

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(5)


@contextlib.contextmanager
def _as_worker(token: str) -> Iterator[None]:
    old = os.environ.get("IASO_WORKER")
    os.environ["IASO_WORKER"] = token
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("IASO_WORKER", None)
        else:
            os.environ["IASO_WORKER"] = old


# ---- starting one ---------------------------------------------------------------------------

def start_detached(root: Path, session: str) -> None:
    """Ask for a worker for ``session``: a detached process, unless a live one has the lock.
    Never waits and never raises (a hook calls this)."""
    root = Path(root)
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("IASO_FAKE_DISPATCH"):
        return None          # a test that queues a job does not start a process of its own
    try:
        path = files.lock_path(root, session)
        if path.exists() and _lock_is_held(root, session, path):
            return None
        from iaso.background import popen_options

        options = popen_options(root, drop=("IASO_WORKER", "IASO_JOB"))  # no console window
        subprocess.Popen([sys.executable, "-m", "iaso", "understand", "worker", "--session",
                          session, "--root", str(root)], **options)
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
    from iaso import log

    return any(e.payload.get("job") == job and detail_part in str(e.payload.get("detail", ""))
               for e in log.read(core.paths, "events", ["job-note"]))


def _write_applied(core: Any, session: str, applied: Applied) -> None:
    """What applying changed, written by the worker: log entries, then notes."""
    from itertools import groupby

    from iaso import log
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
        self.guard = threading.Lock()      # SR-387: one thread writes at a time

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
            from iaso import debug

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
        from iaso.understand.kinds import KINDS

        try:
            return str(KINDS[job.kind].describe(job))
        except Exception:  # noqa: BLE001 - a kind with no words says its name
            return job.kind

    def _progress(self, job: Job) -> Any:
        from iaso.progress import Reporter

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
        prep = self._prepare(job, started, t0)
        if prep is None:
            return
        module, job, reporter, step, counts = prep
        interval = float(getattr(self.core.config.understand, "progress_interval_s", 1) or 1)
        with _Ticker(self, reporter, step, interval, counts):
            got = self._call(module, job)
        self._conclude(module, job, reporter, got, started, t0)

    def _prepare(self, job: Job, started: str, t0: float) -> tuple[Any, Job, Any, str, tuple[int, int]] | None:
        """What execute does before the model call; None when the job ended here."""
        from iaso.understand.kinds import KINDS

        try:
            module = KINDS[job.kind]
        except (KeyError, ImportError) as exc:
            self._error(job, "kind", f"no job kind {job.kind!r} ({exc})", started, t0)
            return None
        reporter = self._progress(job)
        step = self._step_text(job)
        counts = self._carried(reporter)
        with contextlib.suppress(Exception):
            reporter.update(step, *counts)
        try:
            recomputed = module.recompute(self.core, job)
        except Exception as exc:  # noqa: BLE001 - a kind that fails is an error result
            self._error(job, "inputs", f"{type(exc).__name__}: {exc}", started, t0)
            return None
        if recomputed is None:
            self._clear(reporter)
            _note(self.core, job.kind, job.id, "nothing left to check; no model was asked")
            self._finish(job, JobResult(job=job.id, status="ok", started=started,
                                        finished=jobs.now(),
                                        run_s=round(time.perf_counter() - t0, 3)))
            return None
        if files.canonical(recomputed) != files.canonical(job.inputs):
            _note(self.core, job.kind, job.id,
                  "the inputs in the job file differ from the ones recomputed from the logs; "
                  "the recomputed ones are used")
            job = dataclasses.replace(job, inputs=dict(recomputed),
                                      inputs_digest=files.digest_of(recomputed))
        step = self._step_text(job)
        with contextlib.suppress(Exception):
            reporter.update(step, *counts)
        return module, job, reporter, step, counts

    def _conclude(self, module: Any, job: Job, reporter: Any, got: tuple[Any, ...],
                  started: str, t0: float) -> None:
        """What execute does after the call: the line, the schema check, apply, the result."""
        if got[-1]:
            self._say(got[-1])
        if got[0] == "err":
            if got[3]:    # SR-217 EX-4: a configured dispatcher failed: said once
                self._unreached(module)
            self._error(job, got[1], got[2], started, t0, got[3])
            return
        _, answer, dname, left, _line = got
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

    def _say_once(self, line: str) -> None:
        """SR-217 EX-4: a line said once in the session window (``Told``)."""
        from iaso.understand.summary import Told, _iso

        told = Told(self.root, self.session, _iso(time.time()))
        if line and line not in told.notices:
            told.notices.add(line)
            told.dirty = True
            told.save()
            self._say(line)

    def _unreached(self, module: Any) -> None:
        if getattr(module, "UNREACHABLE", ""):
            self._say_once(module.UNREACHABLE)

    def _call(self, module: Any, job: Job, guard: Any = None) -> tuple[Any, ...]:
        """SR-387: the one way to ask. No side effect on results, the ledger, failures.json, the
        progress file or the session's lines, so it may run in a thread: ``("ok", answer,
        dispatcher, left, line)`` or ``("err", step, message, dispatcher, line)``. With a
        ``guard`` (a Lock the calling thread holds) it is let go only while the model is out."""
        cascade = getattr(module, "cascade", None)
        if cascade is not None:             # SR-182: the kind chooses who answers
            try:
                done = cascade(self.core, job, system=agents.load(job.kind),
                               schema=module.schema, **({"guard": guard} if guard else {}))
            except module.Waiting as wait:
                return "err", "dispatch", str(wait.cause), "", wait.line or ""
            except DispatchError as exc:
                return "err", exc.step, exc.message, "", ""
            except Exception as exc:  # noqa: BLE001 - any failure of a judge is the job's
                return "err", "run", f"{type(exc).__name__}: {exc}", "", ""
            return "ok", done.answer, done.dispatcher, done.left, done.line or ""
        scale = dispatch.budget_scale.set(budget_scale_for(self.root, self.session))
        try:
            dispatcher = dispatch.configured(self.core)
        except NoModel as exc:
            return "err", "dispatch", str(exc), "", ""
        finally:
            dispatch.budget_scale.reset(scale)
        reason = dispatcher.available()
        if reason:
            return "err", "dispatch", reason, dispatcher.name, ""
        if guard:
            dispatcher = dispatch.Unlocked(dispatcher, guard)
        try:
            answer = dispatcher.run(
                job, system=agents.load(job.kind),
                user=json.dumps(job.inputs, ensure_ascii=False, sort_keys=True, indent=1),
                schema=module.schema, on_step=lambda text: None)
        except DispatchError as exc:
            return "err", exc.step, exc.message, dispatcher.name, ""
        except Exception as exc:  # noqa: BLE001 - any failure of a dispatcher is the job's
            return "err", "run", f"{type(exc).__name__}: {exc}", dispatcher.name, ""
        return "ok", dict(answer), dispatcher.name, (), ""

    def _threaded(self, module: Any, job: Job) -> tuple[Any, ...]:
        """_call in a pool thread. Everything the kinds and dispatchers write while asking (the
        log, records, caches, judge state) happens under ``self.guard``, which only the model
        call itself lets go of, so two threads never write at once."""
        with self.guard:
            return self._call(module, job, self.guard)

    def _batch(self, queue: list[Job], limit: int) -> list[Job]:
        """SR-387: up to ``limit`` jobs, in queue order, that wait for nothing still to run."""
        out: list[Job] = []
        for job in queue:
            if jobs.result(self.root, self.session, job.id) is not None:
                continue
            if job.needs:
                need = jobs.result(self.root, self.session, job.needs)
                if need is None or need.status != "ok":
                    continue
            out.append(job)
            if len(out) == limit:
                break
        return out

    def _run_batch(self, batch: list[Job], limit: int) -> None:
        ready = []
        for job in batch:
            self.queued[job.id] = job
            self.seen.add(job.id)
            started, t0 = jobs.now(), time.perf_counter()
            prep = self._prepare(job, started, t0)
            if prep is not None:
                ready.append((job, prep, started, t0))
        if not ready:
            return
        _, (module, sent, reporter, step, counts), _, _ = ready[0]
        interval = float(getattr(self.core.config.understand, "progress_interval_s", 1) or 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=limit) as pool, \
                _Ticker(self, reporter, f"{step} ({len(ready)} checks out)", interval, counts):
            futures = [pool.submit(self._threaded, p[0], p[1]) for _, p, _, _ in ready]
            answers = [f.result() for f in futures]
        for (job, (module, sent, reporter, _step, _counts), started, t0), got in zip(
                ready, answers, strict=True):
            # an earlier answer of the batch may have changed the logs (a kind that settles
            # its own job says stale_check = False)
            if got[0] == "ok" and getattr(module, "stale_check", True):
                try:
                    now = module.recompute(self.core, sent)
                except Exception:  # noqa: BLE001 - execute reports it
                    now = None
                if now is None or files.canonical(now) != files.canonical(sent.inputs):
                    self.execute(job, jobs.now(), time.perf_counter())
                    continue
            self._conclude(module, sent, reporter, got, started, t0)
        self._clear(ready[0][1][2])

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
        limit = int(self.core.config.understand.parallel_calls)
        while True:
            waiting = [j for j in jobs.queued(self.root, self.session) if j.id not in seen]
            if not waiting:
                break
            if limit > 1 and len(batch := self._batch(waiting, limit)) > 1:
                seen.update(j.id for j in batch)
                self._run_batch(batch, limit)
                continue
            job = waiting[0]
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
        with _beating(root, session, token):
            return _run_locked(core, session, token, job_id)
    finally:
        release(root, session, token)


def run_loop(core: Any, session: str) -> None:
    """Run jobs until none is left (the worker's loop). The lock is let go before the last look
    at the queue, so a job queued as the worker leaves starts a worker of its own."""
    if core is None:
        return None
    root = Path(core.root)
    from iaso.understand.summary import AFTER_STOP, after_stop

    idle_looks = 0
    while True:
        token = acquire(root, session)
        if token is None:
            return None
        try:
            with _beating(root, session, token):
                try:
                    # SR-375: what a turn end left for the background, under the lock (done
                    # outside it, each turn end met no lock and started one more worker);
                    # looked at on every pass, since a stop that found this worker holding
                    # the lock started no worker of its own
                    after_stop(core, session)
                except Exception:  # noqa: BLE001 - the jobs still run
                    pass
                ran = _run_locked(core, session, token, None)
        finally:
            release(root, session, token)
            forget = getattr(core, "forget_log", None)
            if forget is not None:   # the worker lives long: no pass keeps the log (report-30e224a3)
                forget()
        if ran:
            idle_looks = 0
        elif idle_looks >= 3 or not (jobs.pending(root, session)
                                     or (files.session_dir(root, session) / AFTER_STOP).exists()):
            return None
        else:
            idle_looks += 1
            time.sleep(0.2)
