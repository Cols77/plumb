"""The trial (JUDGE, SR-106, SR-133, DEC-038).

No trial card is drawn any more (SR-252 EX-6): a record the judge model finds supported is
not put to the owner and waits for JEV (SR-372). What stays: the calibrated threshold, the
owner's words a record came from, and the reading of a trial card an older session still holds
(``card`` rebuilds its shape, ``effect`` logs its answer). Recalibration reads the logged
scores (``capture.calibrate``) and calls no model."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from plumb.contracts import Applied, CardState, Choice, ClarifyQuestion
from plumb.understand import cards

WORDS_PER_ITEM = 140
NOT_FOUND = "Your words for this were not found."
NO_WORDS = 'The words of yours "{title}" came from are not on file.'
ASK = "Is this what you meant?"
CHOICES = (
    Choice("Yes", "accepted", consequence="It is confirmed as yours."),
    Choice("No", "rejected", consequence="It is marked as a misreading and stays unconfirmed."),
    Choice("Fix it", "change",
           consequence="You say what it should be; it stays unconfirmed until then."))


@dataclass(frozen=True)
class Candidate:
    """A supported record waiting for the owner."""

    record: Any
    score: float
    premise: Mapping[str, Any]
    reason: str = ""


# --------------------------------------------------------------------------- thresholds


def claim_kind(record_kind: str) -> str | None:
    from plumb.capture.calibrate import KINDS

    return KINDS.get(record_kind)


def threshold(core: Any, record_kind: str) -> float:
    """The score at which the judge would confirm a ``record_kind`` record: the latest judge
    calibration's threshold for the kind when it passes, else the starting value."""
    from plumb.capture.calibrate import judge_calibrations

    start = float(core.config.understand.reader_threshold_start)
    kind = claim_kind(record_kind)
    for calibration in reversed(judge_calibrations(core)):
        per_kind = calibration.payload.get("per_kind")
        result = per_kind.get(kind) if isinstance(per_kind, Mapping) and kind else None
        if isinstance(result, Mapping):
            if result.get("passing") and result.get("threshold") is not None:
                return float(result["threshold"])
            return start
    return start


# --------------------------------------------------------------------------- the card


def _date(at: str) -> str:
    try:
        day = datetime.strptime(str(at)[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{day.day} {day:%b}"


def _said(words: str, at: str) -> str:
    return f'"{cards.clip(words, WORDS_PER_ITEM)}"' + (f" ({_date(at)})" if _date(at) else "")


def _prompts(core: Any) -> list[dict[str, Any]]:
    out = []
    for line in core.paths.prompt_lines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _prompt_for(prompts: list[dict[str, Any]], digest: str) -> dict[str, Any] | None:
    want = digest.removeprefix("sha256:").strip()
    if not want:
        return None
    for entry in prompts:
        if str(entry.get("digest") or "").removeprefix("sha256:").startswith(want):
            from plumb.hosts.claude_code.prompt import owner_text

            return {"text": owner_text(str(entry.get("text") or "")),
                    "at": str(entry.get("at") or "")}
    return None


def recovered(core: Any, source: Any) -> dict[str, Any] | None:
    """What ``plumb quotes recover`` found for ``source`` in past transcripts (SR-118), or
    None: ``{status, span, at, session, reason, proposed_wording, note}``. Shown, never
    trusted: ``note`` says it was found in a transcript and is not verified."""
    from plumb.understand.recover import finding_for

    try:
        finding = finding_for(core, source)
    except Exception:  # noqa: BLE001 - an unreadable cache shows nothing, it never breaks a card
        return None
    if finding is None:
        return None
    keys = ("status", "span", "at", "session", "reason", "proposed_wording", "note", "by")
    return {key: finding.get(key) for key in keys}


def found_lines(found: Mapping[str, Any] | None) -> list[str]:
    """What a transcript search found (``recovered``) in plain words, or [] when nothing."""
    if not found:
        return []
    from plumb.understand.recover import finding_lines

    return finding_lines(found)


def owner_words(core: Any, record: Any) -> dict[str, Any]:
    """The owner's words ``record`` traces to: for itself when it is an intent, and for each
    intent it derives from, the quote and the logged prompt it came from (where on file).
    ``{"items": [{id, title, quote, prompt, at, found, found_lines}], "note": ""}``; ``note``
    says plainly when none is on file. ``found`` is what a transcript search found
    (``recovered``): shown as found, not verified, it never stands for the owner's logged
    words."""
    index = core.index()
    sources = [record] if record.kind == "intent" else []
    sources += [index[link.target.record] for link in record.links
                if link.kind == "derives_from" and link.target.record in index]
    prompts = _prompts(core) if sources else []
    items = []
    for source in sources:
        raw = source.fields.get("quote") or ""
        parts = raw if isinstance(raw, (list, tuple)) else [raw]   # some intents quote twice
        quote = " / ".join(" ".join(str(p).split()) for p in parts if str(p).strip())
        prompt = _prompt_for(prompts, str(source.fields.get("prompt") or ""))
        found = recovered(core, source)
        if not quote and prompt is None and found is None:
            continue
        items.append({"id": source.id, "title": source.title, "quote": quote or None,
                      "prompt": prompt["text"] if prompt else None,
                      "at": prompt["at"] if prompt else None, "found": found,
                      "found_lines": found_lines(found)})
    return {"items": items, "note": "" if items else NO_WORDS.format(title=record.title)}


def _evidence(core: Any, record: Any) -> str:
    """The owner's words this record came from, with their date, or that they were not found."""
    for item in owner_words(core, record)["items"]:
        found = item.get("found") or {}
        if found.get("status") == "found" and found.get("span"):    # found by meaning
            return _said(found["span"], found.get("at") or "")
        if item.get("quote"):                          # then the owner's own quoted words
            return _said(item["quote"], item.get("at") or "")
        if item.get("prompt") and item.get("at"):
            return _said(item["prompt"], item["at"])
    return _request_of(core, record) or NOT_FOUND


def _request_of(core: Any, record: Any) -> str:
    """The request the record was written for, with its date, when its prompt is on file."""
    from plumb.approvals import Refused, find_prompt

    digest = str(record.fields.get("prompt") or "")
    try:
        logged = find_prompt(core, digest)
    except Refused:
        return ""
    at = str(logged.get("at") or logged.get("time") or logged.get("ts") or "")
    return NOT_FOUND + " It came from your request " + _said(str(logged.get("text") or ""), at)


def _proposal(record: Any) -> str:
    """What the record says, in the owner's terms."""
    from plumb.understand.judge import _flat, _items

    fields = record.fields
    if record.kind == "intent":
        return _flat(fields.get("readback") or record.title)
    if record.kind == "decision":
        chosen = _flat(fields.get("chosen"))
        others = ", ".join(_items(fields.get("alternatives")))
        return f"You chose {chosen}" + (f" over {others}" if others else "")
    return _flat(fields.get("statement") or record.title)


def card(core: Any, item: Candidate) -> CardState:
    """The read-back of one record as a trial card."""
    record = item.record
    short = str(record.hash).split(":")[-1][:12]
    cid = f"trial:{record.id}@{short}"
    labels = tuple(c.label for c in CHOICES)
    return CardState(
        id=cid, kind="trial", topic=record.title,
        issue=_proposal(record),
        evidence=_evidence(core, record), resolutions=labels,
        questions=(ClarifyQuestion(id=f"{cid}#1", text=ASK, resolutions=labels,
                                   record=record.id, hash=record.hash, choices=CHOICES),))


# --------------------------------------------------------------------------- the answer


def effect(*, core: Any = None, card: CardState | None = None, **_: Any) -> Applied | None:
    """A trial card was answered (READ confirmed the yes, labelled yes, or rejected the no):
    log the answer."""
    if card is None or core is None:
        return None
    answered = {a.question: a.answer for a in card.answers}
    if not card.questions or any(q.id not in answered for q in card.questions):
        return None
    items = [{"id": q.record, "hash": q.hash} for q in card.questions]
    answers = [{"question": q.id, "answer": answered[q.id]} for q in card.questions]
    return Applied(entries=({"kind": "trial", "payload": {
        "card": card.id, "items": items, "answers": answers}},))
