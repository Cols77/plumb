"""The pushback job kind (SR-362, DEC-340): the agent sent one of the judge's questions back as
obvious or already answered, with its reason (``plumb question pushback``).

The judge reads the question and the reason against the owner's own logged words
(``premise.owner_words``) and the approved records (SR-218's withdrawal: the tidy job's
``_confirmed`` and its exact-quote check) and withdraws the question, quoting what answers it,
or keeps it. ``apply`` withdraws only when the quote is really in the owner's words or in an
approved record; unsure, or words found nowhere, keep it. Either ruling is logged as
``question-ruling`` with the agent's reason; a withdrawn question counts as answered
(``judge.unanswered``). Nothing else drops a judge question."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text
from plumb.understand import files, read

kind = "pushback"
SCHEMA_ID = "pushback.v1"
HERE = Path(__file__).resolve().parent


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "pushback.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def _inputs(core: Any, session: str, key: str, reason: str) -> dict[str, Any] | None:
    """The question still open under ``key``, the agent's reason, the owner's words and the
    approved records; None once the question is no longer open (nothing to rule on)."""
    from plumb.understand import judge, premise, tidy

    found = next((q for q in judge.open_questions(core, session) if q.get("key") == key), None)
    if found is None:
        return None
    # shortcut: every logged owner word and approved record is sent, as tidy does; upgrade to
    # the ones `core.relevant` picks when the prompt grows too big
    return {"key": key, "reason": reason, "question": str(found.get("question") or ""),
            "options": [str(o.get("label") or "") for o in found.get("options") or ()
                        if isinstance(o, Mapping)],
            "said": list(dict.fromkeys(t for t, _ in premise.owner_words(core) if t.strip())),
            "confirmed": [{"id": i, "text": t} for i, t in tidy._confirmed(core).items()]}


def build(core: Any, session: str, *, key: str, reason: str, **_: Any) -> Job | None:
    inputs = _inputs(core, session, key, reason) if core is not None else None
    return None if inputs is None else files.make_job(kind, session, SCHEMA_ID, inputs)


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    if core is None:
        return None
    return _inputs(core, job.session, str(job.inputs.get("key")),
                   str(job.inputs.get("reason") or ""))


def describe(job: Job) -> str:
    return owner_text.STEP_PUSHBACK


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    """SR-362 EX-2, EX-3: withdrawn when the judge says so and its quote is verbatim in the
    owner's words (``by: owner``) or an approved record (``by``: its id); else kept, its
    meaning unchanged. EX-4: both are logged with the reason."""
    inputs = job.inputs
    quote = " ".join(str(answer.get("quote") or "").split())
    by = ""
    if answer.get("verdict") == "withdraw" and quote:
        by = next((str(r.get("id")) for r in inputs.get("confirmed") or ()
                   if isinstance(r, Mapping) and read.evidence_in(quote, str(r.get("text")))),
                  "") or ("owner" if any(read.evidence_in(quote, str(s))
                                         for s in inputs.get("said") or ()) else "")
    payload = {"session": job.session, "job": job.id, "key": inputs.get("key"),
               "question": inputs.get("question"), "reason": inputs.get("reason"),
               "ruling": "withdrawn" if by else "kept"}
    if by:
        payload.update(quote=quote, by=by)
    return Applied(job=job.id, entries=({"kind": "question-ruling", "payload": payload},))
