"""The clarify job kind. Stub: nothing is built (phase C)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text

kind = "clarify"
schema: Mapping[str, Any] = {"id": "clarify.v1"}


def build(core: Any, session: str, **context: Any) -> Job | None:
    return None


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    return None


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    return Applied(job=job.id)


def describe(job: Job) -> str:
    return owner_text.STEP_CHECKING


def on_prompt(ctx: Any, core: Any, entry: Any, *, after: str | None = None) -> list[str]:
    """Queue the clarify job (its ``needs`` is ``after``); agent-facing lines."""
    return []
