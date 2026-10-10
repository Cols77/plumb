"""The read job kind. Stub: nothing is built (phase C)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text

kind = "read"
schema: Mapping[str, Any] = {"id": "read.v1"}


def build(core: Any, session: str, **context: Any) -> Job | None:
    return None


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    return None


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    return Applied(job=job.id)


def describe(job: Job) -> str:
    return owner_text.STEP_READING


def on_prompt(ctx: Any, core: Any, entry: Any) -> str | None:
    """Queue the read job of this message; the id of the job queued, or None."""
    return None
