"""The job queue (ENGINE): hooks queue and return; the worker runs.

``enqueue`` writes the job file (atomic, idempotent: the same inputs are the same id, so a
retried hook never queues twice, and a job that has a result is not queued again; changed
inputs make a new id) and asks for a worker without waiting for it. Inside a job's own session
(``PLUMB_JOB``) nothing is queued. The failure side (``failures``, ``retry_failed``,
``consecutive_failures``) reads what the worker wrote."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from plumb.contracts import Job, JobResult
from plumb.understand import files, jobs, ledger, worker


def enqueue(core: Any, job: Job) -> None:
    if core is None or os.environ.get("PLUMB_JOB"):
        return None                       # a job never queues jobs (SR-104 EX-2)
    root = Path(core.root)
    path = jobs.job_path(root, job.session, job.id)
    if path.exists():
        if jobs.result(root, job.session, job.id) is not None:
            return None                   # already answered; the inputs are the same
    else:
        stamped = job if job.created else files.make_job(
            job.kind, job.session, job.schema, job.inputs, needs=job.needs,
            created=jobs.now())
        files.write_json_atomic(path, files.job_to_json(stamped))
    worker.start_detached(root, job.session)
    return None


def retry_failed(core: Any, session: str) -> list[str]:
    """Queue again the jobs whose result is an error (once per call; the worker runs a
    ``needs`` job before its dependent). Returns the ids put back."""
    if core is None or os.environ.get("PLUMB_JOB"):
        return []
    root = Path(core.root)
    again: list[str] = []
    for outcome in failures(core, session):
        if jobs.load(root, session, outcome.job) is None:
            continue
        try:
            jobs.result_path(root, session, outcome.job).unlink()
        except OSError:
            continue
        ledger.forget(root, session, outcome.job)
        again.append(outcome.job)
    if again:
        worker.start_detached(root, session)
    return again


def failures(core: Any, session: str) -> list[JobResult]:
    """The error results whose job has no ok result, oldest first (the "couldn't check" line)."""
    if core is None:
        return []
    root = Path(core.root)
    folder = files.results_dir(root, session)
    found = [r for p in sorted(folder.glob("*.json")) if folder.is_dir()
             and (r := jobs.result(root, session, p.stem)) is not None and r.status == "error"
             and jobs.load(root, session, p.stem) is not None]
    return sorted(found, key=lambda r: (r.started, r.job))


def consecutive_failures(root: Path, session: str) -> int:
    """The ``consecutive`` count of ``failures.json`` (0 when there is no file)."""
    data = files.read_json(files.failures_path(Path(root), session))
    try:
        return int(data.get("consecutive") or 0) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        return 0
