"""The job queue (ENGINE). Stub: nothing is queued."""

from __future__ import annotations

from typing import Any

from plumb.contracts import Job


def enqueue(core: Any, job: Job) -> None:
    return None


def retry_failed(core: Any, session: str) -> list[str]:
    return []
