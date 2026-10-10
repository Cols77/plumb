"""The judge job kind. Stub: nothing is built (phase C)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text

kind = "judge"
schema: Mapping[str, Any] = {"id": "judge.v1"}


def build(core: Any, session: str, **context: Any) -> Job | None:
    return None


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    return None


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    return Applied(job=job.id)


def describe(job: Job) -> str:
    return owner_text.STEP_CHECKING


def queue_for_capture(core: Any, result: Any, *, prompt_digest: str | None = None) -> None:
    """Queue the judge job for the records a capture wrote."""
    return None
