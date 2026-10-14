"""The tidy job kind (SR-162): one model reading per change of the open cards against the
owner's confirmed records, so a card the owner already answered, or one that repeats another,
is withdrawn without waiting for them.

``build`` and ``recompute`` take the cards and the confirmed records from the logs; ``apply``
withdraws only after exact checks: the record is really confirmed and the quoted words are
really in it, or the other card is really still open. A withdrawal answers and confirms
nothing. Unsure is ``keep``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text
from plumb.understand import cardstore, files, read

kind = "tidy"
SCHEMA_ID = "tidy.v1"
HERE = Path(__file__).resolve().parent


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "tidy.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def _confirmed(core: Any) -> dict[str, str]:
    """``{id: text}`` of the records the owner confirmed and nothing replaced."""
    index = core.index()
    return {i: read.record_text(index[i]) for i, s in core.status(list(index)).items()
            if s.confirmation == "confirmed" and s.superseded_by is None and i in index}


def _inputs(core: Any, session: str) -> dict[str, Any] | None:
    cards = [{"id": c.id, "kind": c.kind, "topic": c.topic, "issue": c.issue,
              "questions": [q.text for q in c.questions]}
             for c in cardstore.load(core.root, session)]
    # shortcut: every confirmed record is sent, so a very large record set makes a big prompt;
    # upgrade to the records `core.relevant` picks per card when that costs too much
    if not cards:
        return None
    return {"cards": cards,
            "confirmed": [{"id": i, "text": t} for i, t in _confirmed(core).items()]}


def build(core: Any, session: str, **context: Any) -> Job | None:
    inputs = _inputs(core, session) if core is not None else None
    return None if inputs is None else files.make_job("tidy", session, SCHEMA_ID, inputs)


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    return _inputs(core, job.session) if core is not None else None


def describe(job: Job) -> str:
    return owner_text.STEP_TIDYING


def enqueue(core: Any, session: str) -> None:
    """Queue the job for the cards open now; it never waits for the model."""
    from plumb.understand import queue

    job = build(core, session)
    if job is not None:
        queue.enqueue(core, job)


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    confirmed = _confirmed(core)
    for verdict in answer.get("verdicts") or ():
        open_cards = {c.id: c for c in cardstore.load(core.root, job.session)}
        card = open_cards.get(str(verdict.get("card")))
        if card is None:
            continue
        if verdict.get("verdict") == "withdraw_answered":
            record, quote = str(verdict.get("record")), str(verdict.get("quote"))
            if record in confirmed and read.evidence_in(quote, confirmed[record]):
                cardstore.withdraw_card(core, job.session, card, owner_text.TIDY_ANSWERED.format(
                    record=record, quote=quote))
        elif verdict.get("verdict") == "withdraw_duplicate":
            other = open_cards.get(str(verdict.get("other")))
            if other is not None and other.id != card.id:
                cardstore.withdraw_card(core, job.session, card, owner_text.TIDY_DUPLICATE.format(
                    other=other.topic))
    return Applied(job=job.id)
