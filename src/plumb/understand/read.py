"""The read job kind (SR-101): one model reading per turn of the owner's free-prose message
against the records the previous reply showed and the open cards.

``build`` (queue side) assembles the job from the logs; ``recompute`` (worker side) rebuilds
the inputs from the logs alone, so a job file the agent wrote is never trusted; ``apply``
confirms only after exact checks (task R2)."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, Job
from plumb.present import owner_text
from plumb.understand import files

kind = "read"
SCHEMA_ID = "read.v1"
HERE = Path(__file__).resolve().parent


def _load_schema() -> Mapping[str, Any]:
    try:
        data = json.loads((HERE / "schemas" / "read.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**data, "id": SCHEMA_ID}


schema: Mapping[str, Any] = _load_schema()


def system_prompt() -> str:
    try:
        return (HERE / "agents" / "read.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- the logs


def _prompt_entries(core: Any) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    try:
        with open(core.paths.prompts, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, Mapping):
                    out.append(item)
    except OSError:
        pass
    return out


def logged_prompt(core: Any, digest: str) -> Mapping[str, Any] | None:
    """The latest prompt-log entry with ``digest`` whose text hashes to it, else None: the
    owner's words as the hook logged them, the only message a confirmation may rest on."""
    from plumb.approvals import prompt_digest
    from plumb.normalize import sha256_text

    found = None
    for item in _prompt_entries(core):
        if item.get("digest") != digest:
            continue
        text = item.get("text")
        if isinstance(text, str) and digest in (prompt_digest(text), sha256_text(text)):
            found = item
    return found


def stated_records(core: Any, prompt_at: str = "") -> dict[str, tuple[str, bool]]:
    """``{id: (hash, shown)}`` of the reply before the prompt (``stated.json``); empty when
    that file was written after the prompt (then it is not the reply the owner answered)."""
    try:
        data = json.loads(core.paths.stated.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, Mapping):
        return {}
    stated_at = str(data.get("at") or "")
    if stated_at and prompt_at and stated_at > prompt_at:
        return {}
    out: dict[str, tuple[str, bool]] = {}
    for item in data.get("records") or []:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            out[item["id"]] = (str(item.get("hash") or ""), item.get("shown") is not False)
    return out


def record_text(record: Any) -> str:
    """The text of a record as the owner is shown it: title, statement and examples."""
    parts = [str(record.title)]
    statement = record.fields.get("statement") if hasattr(record, "fields") else None
    if statement:
        parts.append(str(statement))
    for example in getattr(record, "examples", ()) or ():
        if example.given or example.when or example.then:
            parts.append(f"given {example.given}, when {example.when}, then {example.then}")
    return " | ".join(" ".join(p.split()) for p in parts if p)


def card_item_id(card: Any, question: Any | None) -> str:
    return card.id if question is None else f"{card.id}/{question.id}"


def card_items(core: Any, session: str) -> list[dict[str, Any]]:
    """The open cards as read inputs: one item per card question (one for a card with none)."""
    from plumb.understand import cardstore

    index = core.index()
    items: list[dict[str, Any]] = []
    for card in cardstore.load(core.root, session):
        questions = list(card.questions) or [None]
        for question in questions:
            record = getattr(question, "record", None)
            items.append({
                "id": card_item_id(card, question), "card": card.id,
                "question": getattr(question, "id", ""), "kind": card.kind,
                "text": getattr(question, "text", "") or card.issue or card.topic,
                "resolutions": list(getattr(question, "resolutions", ()) or card.resolutions),
                "record": record, "hash": index[record].hash if record in index else ""})
    return items


def shown_items(core: Any, prompt_at: str = "") -> list[dict[str, Any]]:
    index = core.index()
    stated = stated_records(core, prompt_at)
    return [{"id": rid, "hash": index[rid].hash, "text": record_text(index[rid])}
            for rid, (stated_hash, shown) in stated.items()
            if shown and rid in index and index[rid].hash == stated_hash]


# --------------------------------------------------------------------------- the kind


def build(core: Any, session: str, **context: Any) -> Job | None:
    """The one read job of this turn, or None when the previous reply stated nothing and no
    card is open (``message``: ``{"digest", "text"}``, else the session's latest prompt)."""
    if core is None:
        return None
    message = context.get("message")
    if not isinstance(message, Mapping):
        mine = [p for p in _prompt_entries(core) if p.get("session") == session]
        message = mine[-1] if mine else None
    if not isinstance(message, Mapping):
        return None
    logged = logged_prompt(core, str(message.get("digest") or ""))
    if logged is None or not str(logged.get("text") or "").strip():
        return None
    shown = shown_items(core, str(logged.get("at") or ""))
    cards = card_items(core, session)
    if not shown and not cards:
        return None
    inputs = {"message": {"digest": logged["digest"], "text": logged["text"]},
              "shown": shown, "cards": cards}
    return files.make_job("read", session, SCHEMA_ID, inputs, created=_utc_now())


def recompute(core: Any, job: Job) -> Mapping[str, Any] | None:
    """The inputs rebuilt from the logs: the message text from the prompt log (not the job
    file), the cards from the card store, the shown records from the stated set of the reply
    before the message. A stated set written after the message is no longer that reply: the
    queued job's own shown records stand, kept only where the record still has that hash."""
    if core is None:
        return None
    claimed = job.inputs.get("message") if isinstance(job.inputs, Mapping) else None
    digest = str(claimed.get("digest") or "") if isinstance(claimed, Mapping) else ""
    logged = logged_prompt(core, digest)
    if logged is None:
        return {"message": {"digest": digest, "text": ""}, "shown": [], "cards": []}
    shown = shown_items(core, str(logged.get("at") or ""))
    if not shown:
        index = core.index()
        shown = [{"id": str(i.get("id")), "hash": str(i.get("hash")),
                  "text": record_text(index[str(i.get("id"))])}
                 for i in job.inputs.get("shown") or ()
                 if isinstance(i, Mapping) and str(i.get("id")) in index
                 and index[str(i.get("id"))].hash == i.get("hash")]
    return {"message": {"digest": logged["digest"], "text": logged["text"]},
            "shown": shown, "cards": card_items(core, job.session)}


def describe(job: Job) -> str:
    return owner_text.STEP_READING


def on_prompt(ctx: Any, core: Any, entry: Any) -> str | None:
    """Queue the read job of this message; the id of the job queued, or None."""
    if core is None or not isinstance(entry, Mapping):
        return None
    session = str(getattr(ctx, "session_id", "") or "")
    job = build(core, session, message=entry)
    if job is None:
        return None
    from plumb.understand import queue, worker

    queue.enqueue(core, job)
    worker.start_detached(core.root, session)
    return job.id


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    return Applied(job=job.id)
