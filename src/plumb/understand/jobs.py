"""Jobs on disk (ENGINE): make them, list them, read their results (plan 3.2 item 2).

The id and the file shapes live in ``files``; this module is the one place that reads the
``jobs/`` and ``results/`` folders. A result is read back only to learn that a job was run and
how it ended; nothing applies from it."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Job, JobResult
from plumb.understand import files, ledger


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_job(kind: str, session: str, schema: str, inputs: Mapping[str, Any], *,
            needs: str | None = None, created: str | None = None) -> Job:
    """A job whose id is fixed by ``(kind, schema, inputs, needs)``."""
    return files.make_job(kind, session, schema, inputs, needs=needs,
                          created=created if created is not None else now())


def job_path(root: Path, session: str, job_id: str) -> Path:
    return files.jobs_dir(root, session) / f"{job_id}.json"


def result_path(root: Path, session: str, job_id: str) -> Path:
    return files.results_dir(root, session) / f"{job_id}.json"


def load(root: Path, session: str, job_id: str) -> Job | None:
    raw = files.read_json(job_path(root, session, job_id))
    return files.job_from_json(raw) if isinstance(raw, Mapping) and raw.get("id") else None


def queued(root: Path, session: str) -> list[Job]:
    """Every job file of the session, oldest first (``created``, then id), the backlog pass's
    judge jobs after the rest: the owner's answer is read before hundreds of waiting records."""
    folder = files.jobs_dir(root, session)
    found = [job for path in sorted(folder.glob("*.json"))
             if (job := load(root, session, path.stem)) is not None] if folder.is_dir() else []
    return sorted(found, key=lambda j: (j.inputs.get("pass") == "backlog", j.created, j.id))


def result(root: Path, session: str, job_id: str, *, trusted: bool = True
           ) -> JobResult | None:
    """The result of a job. By default only one the worker wrote (it has a ledger entry);
    ``trusted=False`` reads any file there, to report it."""
    if trusted and not ledger.has(root, session, job_id):
        return None
    raw = files.read_json(result_path(root, session, job_id))
    return files.result_from_json(raw) if isinstance(raw, Mapping) else None


def write_result(root: Path, session: str, outcome: JobResult) -> None:
    files.write_json_atomic(result_path(root, session, outcome.job), files.result_to_json(outcome))


def pending(root: Path, session: str) -> list[Job]:
    """The queued jobs with no result of the worker's."""
    return [job for job in queued(root, session) if result(root, session, job.id) is None]
