"""The read job kind (SR-101): one model reading per turn of the owner's free-prose message
against the records the previous reply showed and the open cards.

``build`` (queue side) assembles the job from the logs; ``recompute`` (worker side) rebuilds
the inputs from the logs alone, so a job file the agent wrote is never trusted; ``apply``
confirms only after exact checks (task R2)."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, CardState, Choice, ClarifyQuestion, Job
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
    """The owner's own entries of the prompt log (SR-168: a peer's message is not one)."""
    from plumb.approvals import is_owner_entry

    out: list[Mapping[str, Any]] = []
    try:
        with open(core.paths.prompts, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, Mapping) and is_owner_entry(item):
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
    """The open cards as read inputs: one item per card question (one for a card with none).
    An item's ``hash`` is the version of its record the card showed (stored with the question
    when the card was made), never the record's version today. ``choices`` are the question's
    own, else its kind's for its resolutions (a card with no question: a stale link)."""
    from plumb.understand import cardstore

    items: list[dict[str, Any]] = []
    for card in cardstore.load(core.root, session):
        questions = list(card.questions) or [None]
        for question in questions:
            record = getattr(question, "record", None)
            resolutions = tuple(getattr(question, "resolutions", ()) or card.resolutions)
            choices = getattr(question, "choices", ()) or tuple(
                Choice(label, "change", label) for label in resolutions)
            items.append({
                "id": card_item_id(card, question), "card": card.id,
                "question": getattr(question, "id", ""), "kind": card.kind,
                "text": getattr(question, "text", "") or card.issue or card.topic,
                "resolutions": list(resolutions),
                "choices": [files.choice_to_json(c) for c in choices],
                "record": record, "hash": getattr(question, "hash", "") or ""})
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
    from plumb.understand import typed

    parsed = typed.parse(entry.get("text"))
    if parsed is not None:
        if parsed.command in ("approve", "confirm") and parsed.ids:
            typed.confirm_now(core, parsed, str(entry.get("digest") or ""), session)
            return None                   # exact: the reader is not called
        if parsed.command == "auto-approve":
            typed.switch_now(core, parsed, str(entry.get("digest") or ""), session)
            return None                   # SR-115: the owner's switch, at once
        if parsed.command not in ("approve", "confirm"):
            return None                   # undo, go, settle: typed.on_prompt, clarify
    job = build(core, session, message=entry)
    if job is None:
        return None
    from plumb.understand import queue, worker

    queue.enqueue(core, job)
    worker.start_detached(core.root, session)
    return job.id


# --------------------------------------------------------------------------- applying

ANSWERS = ("accepted", "rejected", "change", "open")
_LOOSE_ID = re.compile(r"^(INT|SR|DEC|FEAT)-0*(\d+)$")


def normalize_id(raw: str, index: Mapping[str, Any]) -> str:
    """The record id the reader meant: ``INT-24`` is ``INT-024``."""
    raw = raw.strip()
    if raw in index:
        return raw
    match = _LOOSE_ID.match(raw.upper())
    if not match:
        return raw
    from plumb.ids import format_id  # the one formatter of record numbers

    return format_id(match.group(1), int(match.group(2)))


def _collapse(text: str) -> str:
    return " ".join(text.split())


def evidence_in(evidence: str, message: str) -> bool:
    """The reader's evidence occurs in the owner's message (whitespace-collapsed)."""
    found = _collapse(evidence)
    return bool(found) and found in _collapse(message)


def _confidence(raw: Any) -> float:
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


def change_card(record: Any, change: str, evidence: str, digest: str) -> CardState:
    """A change the owner asked for in words, read back at the next turn."""
    issue = owner_text.READBACK_CHANGE.format(title=record.title, change=change)
    options = (owner_text.READBACK_YES, owner_text.READBACK_NOT_QUITE)
    question = ClarifyQuestion(id="change", text=issue, resolutions=options, record=record.id,
                               hash=record.hash,
                               choices=(Choice(owner_text.READBACK_YES, "accepted"),
                                        Choice(owner_text.READBACK_NOT_QUITE, "change")))
    return CardState(id=f"change:{record.id}:{digest.removeprefix('sha256:')[:12]}",
                     kind="clarify", topic=record.title, issue=issue, evidence=evidence,
                     resolutions=question.resolutions, questions=(question,), status="open")


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    """Apply the reader's entries after exact checks only (nothing here reads the words):
    the message is in the prompt log; the record was shown at that version and is still that
    version; the evidence occurs in the message; an ``accepted`` entry at or above the
    threshold confirms (``by: owner-words``). Every entry is logged as a ``read-entry``."""
    if core is None:
        return Applied(job=job.id)
    from plumb.understand import answer as answer_mod
    from plumb.understand.threshold import reader_threshold

    inputs = job.inputs if isinstance(job.inputs, Mapping) else {}
    claimed = inputs.get("message") if isinstance(inputs.get("message"), Mapping) else {}
    digest = str(claimed.get("digest") or "")
    logged = logged_prompt(core, digest)
    if logged is None:
        return Applied(job=job.id, notes=("the message is not in the prompt log; "
                                          "nothing was confirmed",))
    work = answer_mod.Answering(core, job.session, job=job, digest=digest,
                                message=str(logged["text"]))
    if digest not in {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}:
        work.entries.append({"kind": "prompt", "payload": {
            "digest": digest, "session": logged.get("session"), "at": logged.get("at")}})
    threshold = reader_threshold(core)
    shown = {str(i["id"]): str(i.get("hash") or "") for i in inputs.get("shown") or ()
             if isinstance(i, Mapping)}
    items = [i for i in inputs.get("cards") or () if isinstance(i, Mapping)]
    by_id = {str(i["id"]): i for i in items}
    by_record = {str(i["record"]): i for i in items if i.get("record")}
    raw_entries = answer.get("entries") if isinstance(answer, Mapping) else None
    for raw in raw_entries or ():
        if not isinstance(raw, Mapping):
            continue
        raw_id = str(raw.get("id") or "")
        name = normalize_id(raw_id, work.index)
        said = str(raw.get("answer")) if raw.get("answer") in ANSWERS else "open"
        confidence = _confidence(raw.get("confidence"))
        evidence = str(raw.get("evidence") or "")
        claimed_hash = str(raw.get("hash") or "")
        work.entries.append({"kind": "read-entry", "payload": {
            "job": job.id, "id": name, "hash": claimed_hash, "answer": said,
            "confidence": confidence, "evidence": evidence, "message_digest": digest}})
        if said == "open":
            continue
        if not evidence_in(evidence, work.message):
            work.notes.append(f"the words quoted for {name} are not in the message; "
                              "nothing was changed")
            continue
        passes = confidence >= threshold
        item = by_id.get(raw_id) or by_id.get(name) or by_record.get(name)
        if item is not None:      # a record on a card is confirmed only by the card's answer
            answer_mod.apply_answer(
                work, card=str(item.get("card")), question=str(item.get("question") or ""),
                record=str(item.get("record") or ""), hash=str(item.get("hash") or ""),
                choice=Choice(answer=said, change=raw.get("change")),
                source=answer_mod.OwnerWords(job=job, digest=digest, evidence=evidence,
                                             confidence=confidence, passes=passes,
                                             rejection=raw.get("rejection")))
            continue
        record = work.index.get(name)
        if record is None:
            continue
        if name in shown and claimed_hash and claimed_hash != shown[name]:
            work.notes.append(f"{name} was answered at a version that was not shown")
            continue
        if name not in shown or shown[name] != record.hash:
            work.notes.append(f"{name} was not shown to the owner at this version; "
                              "nothing was confirmed")
            continue
        if said == "accepted" and passes:
            work.confirm(name, record.hash, evidence, confidence)
        elif said == "rejected":
            work.reject(record, evidence, confidence, raw.get("rejection"))
        elif said == "change":
            card = change_card(record, str(raw.get("change") or evidence), evidence, digest)
            work.cards[card.id] = card
    return work.applied()


# --------------------------------------------------------------------------- card kinds
# An effect handler is called with keywords: core, job, card, question (the question id),
# entry ({answer, change, confidence, evidence, record, hash}), message, digest, accepted
# (accepted at or above the threshold) and confirm (confirm(record, hash, evidence,
# confidence, label=None), the one way an owner-words approval is queued). It returns an
# ``Applied`` or None, and takes ``**_`` for what a later version adds.


def _acknowledge_effect(**_: Any) -> Applied | None:
    """A stale-link card answered: the answer is recorded on the card and the agent
    resolves it; nothing is confirmed or changed here."""
    return None


def _register() -> None:
    from plumb.understand import effects

    effects.register("stale_link", _acknowledge_effect)


_register()


def _switch_lines(core: Any, payload: Mapping[str, Any]) -> list[str]:
    """What the owner is told of their typed ``/plumb auto-approve`` (SR-115): the switch, and
    why it is not in effect yet when it is not."""
    settings = payload.get("auto_approve")
    on = isinstance(settings, Mapping) and bool(settings.get("enabled"))
    lines = [owner_text.AUTO_APPROVE_SWITCHED.format(state="on" if on else "off")]
    if on:
        from plumb.capture.api import auto_approve_state

        state = auto_approve_state(core)
        if state.configured and not state.effective:
            lines = [owner_text.AUTO_APPROVE_NOT_YET.format(reason=state.reason)]
    return lines


def confirmation_lines(core: Any, turn: Any = None) -> list[str]:
    """``<title>: you said: <evidence>`` for each record the owner's words confirmed for a
    message (``turn``: its prompt digest, or a mapping holding ``prompt_digest``; default:
    the latest prompt)."""
    digest = turn.get("prompt_digest") if isinstance(turn, Mapping) else turn
    if not digest:
        logged = _prompt_entries(core)
        digest = logged[-1].get("digest") if logged else None
    index = core.index()
    lines: list[str] = []
    for entry in core.events():
        payload = entry.payload
        if entry.kind == "config" and payload.get("via") == "typed" \
                and payload.get("prompt_digest") == digest:
            lines.extend(_switch_lines(core, payload))
            continue
        if entry.kind != "approval" or payload.get("prompt_digest") != digest:
            continue
        if payload.get("by") == "agent-relayed" and payload.get("via") == "command":
            titles = ", ".join(index[str(r.get("id"))].title for r in payload["records"]
                               if str(r.get("id")) in index)
            lines.append(owner_text.TYPED_CONFIRMED.format(titles=titles))
            continue
        if payload.get("by") != "owner-words":
            continue
        said = owner_text.CONFIRM_YOU_SAID.format(evidence=payload.get("evidence", ""))
        for record in payload.get("records") or ():
            item = index.get(str(record.get("id")))
            lines.append(f"{item.title}: {said}" if item is not None else said)
    return lines
