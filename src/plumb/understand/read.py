"""The read job kind (SR-101): one model reading per turn of the owner's free-prose message
against the records the previous reply showed and the open cards.

``build`` (queue side) assembles the job from the logs; ``recompute`` (worker side) rebuilds
the inputs from the logs alone, so a job file the agent wrote is never trusted; ``apply``
confirms only after exact checks (task R2)."""

from __future__ import annotations

import dataclasses
import json
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Applied, CardState, ClarifyAnswer, ClarifyQuestion, Job
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
    from plumb.understand import typed

    parsed = typed.parse(entry.get("text"))
    if parsed is not None:
        if parsed.command in ("approve", "confirm") and parsed.ids:
            typed.confirm_now(core, parsed, str(entry.get("digest") or ""), session)
            return None                   # exact: the reader is not called
        if parsed.command not in ("approve", "confirm"):
            return None                   # undo, settle and go are their own commands
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
    from plumb.ids import format_id          # the one formatter of record numbers

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


def _approval(core: Any, job: Job, digest: str, message: str, record_id: str,
              record_hash: str, evidence: str, confidence: float, *,
              label: str | None = None) -> dict[str, Any]:
    from plumb.approvals import approval_items

    (item,) = approval_items(core, [record_id])   # with the owned ends and test pins
    payload: dict[str, Any] = {
        "by": "owner-words", "session": job.session, "job": job.id,
        "records": [{**item, "hash": record_hash}], "prompt_digest": digest,
        "message": message, "evidence": evidence, "confidence": confidence}
    if label:
        payload["label"] = label
    return {"kind": "approval", "payload": payload}


def _rejection(core: Any, job: Job, digest: str, record: Any, evidence: str, confidence: float,
               rejection: Any) -> dict[str, Any]:
    from plumb.capture.calibrate import snapshot
    from plumb.normalize import sha256_text

    item = {"id": record.id, "hash": record.hash, **snapshot(core.index(), record, core)}
    return {"kind": "rejection", "payload": {
        "by": "owner-words", "session": job.session, "job": job.id, "records": [item],
        "reason": "capture-error" if rejection == "misread" else "intent-change",
        "prompt_digest": digest, "quote": evidence, "quote_digest": sha256_text(evidence),
        "confidence": confidence}}


def show_first_card(record: Any, evidence: str) -> CardState:
    """The card that shows a record the owner named but never saw, before it can be
    confirmed on the next answer (SR-088's rule, kept for prose)."""
    text = record_text(record)
    issue = owner_text.CARD_SHOW_FIRST.format(topic=record.title, issue=text)
    question = ClarifyQuestion(id="confirm", text=issue,
                               resolutions=("Yes, that is right", "No"), record=record.id)
    return CardState(id=f"show_first:{record.id}", kind="show_first", topic=record.title,
                     issue=issue, evidence=evidence, resolutions=question.resolutions,
                     questions=(question,), status="open")


def change_card(record: Any, change: str, evidence: str, digest: str) -> CardState:
    """A change the owner asked for in words, read back at the next turn."""
    issue = owner_text.READBACK_CHANGE.format(title=record.title, change=change)
    question = ClarifyQuestion(id="change", text=issue,
                               resolutions=("Yes, that is it", "Not quite"), record=record.id)
    return CardState(id=f"change:{record.id}:{digest.removeprefix('sha256:')[:12]}",
                     kind="clarify", topic=record.title, issue=issue, evidence=evidence,
                     resolutions=question.resolutions, questions=(question,), status="open")


def owner_only_reply(card: CardState, question: Any) -> str:
    """What a prose answer to an owner-only card is told: nothing changed, and the button
    or the typed command that does it."""
    if card.kind == "settled_item":
        record = getattr(question, "record", None) or card.topic
        return owner_text.OWNER_ONLY_REPLY.format(action="undo anything",
                                                  command=f"/plumb undo {record}".strip())
    kind = next((w.rstrip("s") for w in card.topic.lower().replace(",", " ").split()
                 if w.rstrip("s") in ("intent", "requirement")), "")
    return owner_text.OWNER_ONLY_REPLY.format(
        action="switch settling on or off", command=f"/plumb settle on {kind}".strip())


def _open_cards(core: Any, session: str) -> list[CardState]:
    from plumb.understand import cardstore

    return cardstore.load(core.root, session)


class _Applying:
    """The state of one ``apply`` (in memory; the caller writes the result)."""

    def __init__(self, core: Any, job: Job, digest: str, message: str) -> None:
        self.core, self.job, self.digest, self.message = core, job, digest, message
        self.index = core.index()
        self.statuses = core.status(list(self.index))
        self.entries: list[Mapping[str, Any]] = []
        self.cards: dict[str, CardState] = {}
        self.closed: list[str] = []
        self.notes: list[str] = []
        self.confirmed: set[str] = set()
        self.open_cards = {c.id: c for c in _open_cards(core, job.session)}

    def confirm(self, record_id: str, record_hash: str, evidence: str, confidence: float,
                label: str | None = None) -> None:
        record = self.index.get(record_id)
        if record is None or record.hash != record_hash or record_id in self.confirmed:
            return
        if self.statuses[record_id].confirmation == "confirmed":
            return
        self.confirmed.add(record_id)
        self.entries.append(_approval(self.core, self.job, self.digest, self.message,
                                      record_id, record_hash, evidence, confidence,
                                      label=label))

    def reject(self, record: Any, evidence: str, confidence: float, rejection: Any) -> None:
        if self.statuses[record.id].confirmation != "confirmed":
            self.entries.append(_rejection(self.core, self.job, self.digest, record, evidence,
                                           confidence, rejection))


def apply(core: Any, job: Job, answer: Mapping[str, Any]) -> Applied:
    """Apply the reader's entries after exact checks only (nothing here reads the words):
    the message is in the prompt log; the record was shown at that version and is still that
    version; the evidence occurs in the message; an ``accepted`` entry at or above the
    threshold confirms (``by: owner-words``). Every entry is logged as a ``read-entry``."""
    if core is None:
        return Applied(job=job.id)
    from plumb.understand.threshold import reader_threshold

    inputs = job.inputs if isinstance(job.inputs, Mapping) else {}
    claimed = inputs.get("message") if isinstance(inputs.get("message"), Mapping) else {}
    digest = str(claimed.get("digest") or "")
    logged = logged_prompt(core, digest)
    if logged is None:
        return Applied(job=job.id, notes=("the message is not in the prompt log; "
                                          "nothing was confirmed",))
    work = _Applying(core, job, digest, str(logged["text"]))
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
        item = by_id.get(raw_id) or by_id.get(name)
        if item is None and name not in shown:
            item = by_record.get(name)
        if item is not None and name not in shown:
            _apply_card(work, item, raw, said, confidence, evidence, passes)
            continue
        record = work.index.get(name)
        if record is None:
            continue
        if name in shown and claimed_hash and claimed_hash != shown[name]:
            work.notes.append(f"{name} was answered at a version that was not shown")
            continue
        if name not in shown or shown[name] != record.hash:
            work.cards[f"show_first:{name}"] = show_first_card(record, evidence)
            continue
        if said == "accepted" and passes:
            work.confirm(name, record.hash, evidence, confidence)
        elif said == "rejected":
            work.reject(record, evidence, confidence, raw.get("rejection"))
        elif said == "change":
            card = change_card(record, str(raw.get("change") or evidence), evidence, digest)
            work.cards[card.id] = card
    return Applied(job=job.id, cards=tuple(work.cards.values()), closed=tuple(work.closed),
                   entries=tuple(work.entries), notes=tuple(work.notes))


def _apply_card(work: _Applying, item: Mapping[str, Any], raw: Mapping[str, Any], said: str,
                confidence: float, evidence: str, passes: bool) -> None:
    """An answer to a card question: recorded on the card, then the effect of the card's
    kind. A prose answer to an owner-only card changes nothing and says what does."""
    from plumb.understand import effects

    card = work.cards.get(str(item.get("card"))) or work.open_cards.get(str(item.get("card")))
    if card is None:
        return
    question = next((q for q in card.questions if q.id == item.get("question")), None)
    if card.kind in effects.NO_EFFECT or card.owner_only:
        work.notes.append(owner_only_reply(card, question))
        return
    if said == "accepted" and not passes:
        return
    record_id = str(item.get("record") or "")
    record = work.index.get(record_id) if record_id else None
    if record is not None and card.kind in ("trial", "backlog") \
            and record.hash == item.get("hash"):
        if said == "accepted":
            work.confirm(record_id, record.hash, evidence, confidence, label="yes")
        elif said == "rejected":
            work.reject(record, evidence, confidence, raw.get("rejection"))
    text = said if said != "change" else f"change: {raw.get('change') or evidence}"
    answers = (*card.answers, ClarifyAnswer(str(item.get("question") or card.id), text,
                                            work.digest))
    answered = {a.question for a in answers}
    done = all(q.id in answered for q in card.questions) if card.questions else True
    card = dataclasses.replace(card, answers=answers, status="answered" if done else "open")
    work.cards[card.id] = card
    if done:
        work.closed.append(card.id)
    handler = effects.handler_for(card.kind)
    if handler is None:
        return
    result = handler(
        core=work.core, job=work.job, card=card, question=item.get("question"),
        entry={"answer": said, "change": raw.get("change"), "confidence": confidence,
               "evidence": evidence, "record": record_id, "hash": item.get("hash")},
        message=work.message, digest=work.digest, accepted=said == "accepted" and passes,
        confirm=work.confirm)
    if isinstance(result, Applied):
        work.entries.extend(result.entries)
        for extra in result.cards:
            work.cards[extra.id] = extra
        work.closed.extend(result.closed)
        work.notes.extend(result.notes)


# --------------------------------------------------------------------------- card kinds
# An effect handler is called with keywords: core, job, card, question (the question id),
# entry ({answer, change, confidence, evidence, record, hash}), message, digest, accepted
# (accepted at or above the threshold) and confirm (confirm(record, hash, evidence,
# confidence, label=None), the one way an owner-words approval is queued). It returns an
# ``Applied`` or None, and takes ``**_`` for what a later version adds.


def _show_first_effect(*, entry: Mapping[str, Any], accepted: bool = False,
                       confirm: Any = None, **_: Any) -> Applied | None:
    """A show_first card answered: the owner has now seen the record, so an accepted answer
    confirms it (at the version the card showed)."""
    if accepted and entry.get("record") and entry.get("hash") and confirm is not None:
        confirm(str(entry["record"]), str(entry["hash"]), str(entry.get("evidence") or ""),
                float(entry.get("confidence") or 0))
    return None


def _acknowledge_effect(**_: Any) -> Applied | None:
    """A link or stale-link card answered: the answer is recorded on the card and the agent
    resolves it; nothing is confirmed or changed here."""
    return None


def _register() -> None:
    from plumb.understand import effects

    effects.register("show_first", _show_first_effect)
    effects.register("link", _acknowledge_effect)
    effects.register("stale_link", _acknowledge_effect)


_register()


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
