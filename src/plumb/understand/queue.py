"""The job queue (ENGINE). Stub: nothing is queued."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plumb.contracts import Job, JobResult
from plumb.understand import stub


def enqueue(core: Any, job: Job) -> None:
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
