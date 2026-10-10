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
from plumb.understand import files, jobs, stub, worker


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
    return []


@stub
def failures(core: Any, session: str) -> list[JobResult]:
    """The error results whose job has no later ok result, oldest first."""
    return []


@stub
def consecutive_failures(root: Path, session: str) -> int:
    """The ``consecutive`` count of ``failures.json`` (0 when there is no file)."""
    return 0
