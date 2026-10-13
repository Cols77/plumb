"""The trial (JUDGE, SR-106, SR-133, DEC-038).

Calibrating the judge takes the owner's answers on records it found ``supported``. Each such
record is asked as one card, the read-back of that record alone: the owner's source words with
their date (or a line saying they were not found), the record's proposal in the owner's terms,
and Yes, No, Fix it. At most ``MAX_OPEN`` are open at a time; while none open is below the
threshold, one record below it is drawn (the threshold is learned on what the owner answers, so
a range cut off at it would teach nothing). The owner's yes confirms the record, labelled yes,
and a no rejects it as a misreading: READ applies both when it applies the answer; ``effect``
logs the answer. Recalibration reads the logged scores (``capture.calibrate``) and calls no
model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from plumb.contracts import Applied, CardState, Choice, ClarifyQuestion
from plumb.understand import backlog, cards

MAX_OPEN = 3
WORDS_PER_ITEM = 140
NOT_FOUND = "Your words for this were not found."
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


# --------------------------------------------------------------------------- the pool


HELD = ("open", "change_requested", "left_open")   # a card the owner has not answered yet


def _open_records(core: Any, session: str) -> set[str]:
    """The records a trial card the owner has not answered still asks about: an open card, one
    waiting for their words, and one they left open (DEC-034: it comes back when its record
    changes, it is not asked again)."""
    from plumb.understand import cardstore

    return {str(q.record) for card in cardstore.own_cards(core.root, session)
            if card.status in HELD and card.kind == "trial"
            for q in card.questions if q.record}


def _rejected(core: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for entry in core.events():
        if entry.kind == "rejection" or (
                entry.kind == "revocation" and entry.payload.get("by") == "undone"):
            for item in entry.payload.get("records") or ():
                if isinstance(item, Mapping):
                    out.add((str(item.get("id")), str(item.get("hash"))))
    return out


def from_log(core: Any, skip: set[str]) -> list[Candidate]:
    """The supported records of the logged verdicts that still wait: judged at their current
    version, neither confirmed nor rejected (nor taken back), not in ``skip``."""
    latest = backlog.latest_verdicts(core)
    index = core.index()
    wanted = [i for i, v in latest.items() if v.get("verdict") == "supported" and i in index
              and index[i].hash == v.get("hash") and i not in skip]
    if not wanted:
        return []
    statuses, rejected = core.status(wanted), _rejected(core)
    return [Candidate(index[i], float(latest[i].get("score") or 0), {}) for i in wanted
            if statuses[i].confirmation != "confirmed" and (i, index[i].hash) not in rejected]


# --------------------------------------------------------------------------- the card


def _date(at: str) -> str:
    try:
        day = datetime.strptime(str(at)[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{day.day} {day:%b}"


def _said(words: str, at: str) -> str:
    return f'"{cards.clip(words, WORDS_PER_ITEM)}"' + (f" ({_date(at)})" if _date(at) else "")


def _evidence(core: Any, record: Any) -> str:
    """The owner's words this record came from, with their date, or that they were not found."""
    from plumb.understand import cardcontent

    for item in cardcontent.owner_words(core, record)["items"]:
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


def cards_for(core: Any, session: str, candidates: Sequence[Candidate], *,
              pass_done: bool = False) -> list[CardState]:
    """The trial cards to open now: this job's supported records ``candidates`` and every one
    the log still holds back, up to ``MAX_OPEN`` open in all. The surest first, but one below
    the threshold when none open is (calibration needs both sides). While a backlog pass runs,
    the log's records wait for its end (``pass_done``: this call is its end)."""
    from plumb.understand import cardstore

    open_ids = [str(q.record) for c in cardstore.own_cards(core.root, session)
                if c.kind == "trial" and c.status in cardstore.AWAITING for q in c.questions]
    room = MAX_OPEN - len(open_ids)
    if room <= 0:
        return []
    held = _open_records(core, session)
    waiting = core.status([c.record.id for c in candidates])      # the judge may have confirmed it
    now = [c for c in candidates if c.record.id not in held
           and waiting[c.record.id].confirmation != "confirmed"]
    skip = held | {c.record.id for c in now} | (
        set() if pass_done else backlog.holding(core, session))
    pool = sorted([*now, *from_log(core, skip)],
                  key=lambda c: (-c.score, c.record.id))
    index, scores = core.index(), backlog.latest_verdicts(core)

    def below(score: float, kind: str) -> bool:
        return score < threshold(core, kind)

    picked: list[Candidate] = []
    if not any(i in index and below(float(scores.get(i, {}).get("score") or 0), index[i].kind)
               for i in open_ids):
        picked = [c for c in pool if below(c.score, c.record.kind)][:1]
    picked += [c for c in pool if c not in picked][:room - len(picked)]
    return [card(core, c) for c in picked]


def top_up(core: Any, session: str) -> list[CardState]:
    """New trial cards for the records still waiting, when fewer than ``MAX_OPEN`` are open
    (called when the turn ends, after a card was answered). A card whose records are all
    confirmed by now (a read-back's yes confirmed them) is withdrawn first, so its slot frees."""
    from plumb.understand import cardstore

    mine = [c for c in cardstore.own_cards(core.root, session) if c.status in cardstore.AWAITING]
    ids = {c.id: [str(q.record) for q in c.questions if q.record] for c in mine}
    status = core.status([r for rs in ids.values() for r in rs])
    done = [i for i, rs in ids.items() if rs and all(status[r].confirmation == "confirmed" for r in rs)]
    if done:
        cardstore.withdraw(core.root, session, done)
    return cards_for(core, session, [])


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
