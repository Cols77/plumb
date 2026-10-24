"""The selfdebug job kind (SR-326): the self-debug workflow of one debug case, run by the
worker in the background. No dispatcher answers it: ``cascade`` runs ``plumb.selfdebug.fix``
(its fixer is the model call) and ``Waiting`` holds the job when no judge can be reached."""

from __future__ import annotations

from typing import Any

from plumb import debug, selfdebug
from plumb.contracts import Applied, Job
from plumb.understand import files
from plumb.understand.verdict import Cascaded, Waiting

__all__ = ["Waiting", "apply", "build", "cascade", "describe", "kind", "recompute", "schema"]

kind = "selfdebug"
SCHEMA_ID = "selfdebug.v1"
schema: dict[str, Any] = {"id": SCHEMA_ID, "type": "object", "required": ["state"],
                          "properties": {"state": {"type": "string"},
                                         "branch": {"type": "string"},
                                         "detail": {"type": "string"}}}


def build(core: Any, session: str, **context: Any) -> Job | None:
    case = context.get("case")
    return files.make_job(kind, session, SCHEMA_ID, {"case": case}) if case else None


def recompute(core: Any, job: Job) -> dict[str, Any] | None:
    """Nothing left to do once the case is resolved (or no longer exists)."""
    return dict(job.inputs) if any(c["id"] == job.inputs.get("case")
                                   for c in debug.open_cases(core.root)) else None


def describe(job: Job) -> str:
    return "fixing a defect in plumb"


def cascade(core: Any, job: Job, **context: Any) -> Cascaded:
    case = next(c for c in debug.open_cases(core.root) if c["id"] == job.inputs["case"])
    out = selfdebug.fix(core, case, locked=True)   # background: take the heavy lock
    if out.state == "held":
        raise Waiting(out.detail, out.line)
    return Cascaded({"state": out.state, "branch": out.branch, "detail": out.detail[:500]},
                    "selfdebug")


def apply(core: Any, job: Job, answer: Any) -> Applied:
    return Applied(job=job.id)
