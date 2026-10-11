"""One answer path for the owner's words and the owner's clicks (sp7-realign-sp8 C5).

``apply_answer`` records an answer on a card question and runs the effect of the card's kind
(the ``effects`` registry). Its ``source`` says where the answer came from:

- ``OwnerWords``: the reader read the owner's message (``read.apply``, after its exact
  checks); an ``accepted`` answer counts only at or above the reader's threshold, and what it
  confirms is logged ``by: owner-words``;
- ``Button``: the owner pressed a drawn card's button (``plumb mod press``); there is
  no threshold, what it confirms is logged ``by: owner, via: button``, Leave open marks the
  card ``left_open`` and Ask for a change marks it ``change_requested`` (status only).

Nothing here writes: ``Answering`` holds what one application changed, the caller writes it."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

from plumb.contracts import Applied, CardState, Choice, ClarifyAnswer, Job
from plumb.present import owner_text

# the kinds of card whose yes confirms a record: the version the card showed
PINNED_KINDS = ("trial", "backlog", "show_first")


@dataclass(frozen=True)
class OwnerWords:
    """The reader's entry for a card question, after its exact checks."""

    job: Job
    digest: str                            # the owner's message, as logged
    evidence: str = ""
    confidence: float = 0.0
    passes: bool = False                   # ``confidence`` is at or above the reader's threshold
    rejection: Any = None                  # the reader's kind of "no" (``misread`` or not)


@dataclass(frozen=True)
class Button:
    """A button the owner pressed on a drawn card: the offer it was drawn as, and the digest
    of the key the press carried (checked against ``mod.json`` by the press)."""

    offer_id: str
    key_digest: str = ""


Source = OwnerWords | Button


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


def _pressed(session: str, button: Button, card: str, question: str) -> dict[str, Any]:
    """What a button entry carries in place of the owner's words (C6)."""
    return {"by": "owner", "via": "button", "session": session, "offer": button.offer_id,
            "key_digest": button.key_digest, "card": card, "question": question}


def _open_cards(core: Any, session: str) -> list[CardState]:
    from plumb.understand import cardstore

    return cardstore.load(core.root, session)


class Answering:
    """The state of one application of answers (in memory; the caller writes the result).
    ``job``, ``digest`` and ``message`` are the reader's (empty for a button press)."""

    def __init__(self, core: Any, session: str, *, job: Job | None = None, digest: str = "",
                 message: str = "") -> None:
        self.core, self.session = core, session
        self.job, self.digest, self.message = job, digest, message
        self.index = core.index()
        self.statuses = core.status(list(self.index))
        self.entries: list[Mapping[str, Any]] = []
        self.cards: dict[str, CardState] = {}
        self.closed: list[str] = []
        self.notes: list[str] = []
        self.confirmed: set[str] = set()
        self.open_cards = {c.id: c for c in _open_cards(core, session)}

    def confirm(self, record_id: str, record_hash: str, evidence: str, confidence: float,
                label: str | None = None, *, pressed: Mapping[str, Any] | None = None) -> None:
        """Queue the approval of ``record_id`` at ``record_hash`` (once, and never of a record
        already confirmed): ``by: owner-words`` from the reader, ``by: owner, via: button``
        when ``pressed`` carries the press."""
        record = self.index.get(record_id)
        if record is None or record.hash != record_hash or record_id in self.confirmed:
            return
        if self.statuses[record_id].confirmation == "confirmed":
            return
        self.confirmed.add(record_id)
        if pressed is None:
            assert self.job is not None
            self.entries.append(_approval(self.core, self.job, self.digest, self.message,
                                          record_id, record_hash, evidence, confidence,
                                          label=label))
            return
        from plumb.approvals import approval_items

        (item,) = approval_items(self.core, [record_id])
        payload = {**pressed, "records": [{**item, "hash": record_hash}]}
        if label:
            payload["label"] = label
        self.entries.append({"kind": "approval", "payload": payload})

    def reject(self, record: Any, evidence: str, confidence: float, rejection: Any, *,
               pressed: Mapping[str, Any] | None = None) -> None:
        if self.statuses[record.id].confirmation == "confirmed":
            return
        if pressed is None:
            assert self.job is not None
            self.entries.append(_rejection(self.core, self.job, self.digest, record, evidence,
                                           confidence, rejection))
            return
        from plumb.capture.calibrate import snapshot

        item = {"id": record.id, "hash": record.hash,
                **snapshot(self.index, record, self.core)}
        self.entries.append({"kind": "rejection", "payload": {
            **pressed, "records": [item],
            "reason": "capture-error" if rejection == "misread" else "intent-change"}})

    def applied(self) -> Applied:
        return Applied(job=self.job.id if self.job is not None else "",
                       cards=tuple(self.cards.values()), closed=tuple(self.closed),
                       entries=tuple(self.entries), notes=tuple(self.notes))


def _close_stale(work: Answering, card: CardState, record: Any, evidence: str) -> None:
    """The record changed after the card showed it: the answer confirms nothing, the card is
    closed, and the version it has now is shown as a fresh card."""
    from plumb.understand.read import show_first_card

    fresh = show_first_card(record, evidence)
    if card.id != fresh.id:
        work.cards[card.id] = dataclasses.replace(card, status="closed")
        work.closed.append(card.id)
    work.cards[fresh.id] = fresh
    work.notes.append(owner_text.CARD_CHANGED_SINCE.format(title=record.title))


def is_left(choice: Choice) -> bool:
    """Whether a pressed ``choice`` leaves the card waiting: Leave open (``open``), or Ask for a
    change (``change`` carrying no wording of its own). A ``change`` choice that carries its
    wording is a pick (a version, a stale link's option) and is applied like any answer."""
    return choice.answer == "open" or (choice.answer == "change" and not choice.change)


def _left(work: Answering, card: CardState, choice: Choice) -> None:
    """Leave open or Ask for a change from a button: nothing is confirmed and no effect runs;
    the card keeps its question and takes the status (``change_requested``: the owner's next
    message is read against it)."""
    status = "left_open" if choice.answer == "open" else "change_requested"
    work.cards[card.id] = dataclasses.replace(card, status=status)


def apply_answer(work: Answering, *, card: str, question: str, record: str, hash: str,
                 choice: Choice, source: Source) -> None:
    """An answer to the question ``question`` of the card ``card`` (``record`` at ``hash``:
    the version the card offered): recorded on the card, then the effect of the card's kind.
    A prose answer to an owner-only card changes nothing and says what does."""
    from plumb.understand import effects
    from plumb.understand.read import owner_only_reply

    state = work.cards.get(card) or work.open_cards.get(card)
    if state is None:
        return
    words = source if isinstance(source, OwnerWords) else None
    asked = next((q for q in state.questions if q.id == question), None)
    if words is None and is_left(choice):     # Leave open, Ask for a change: any card
        _left(work, state, choice)
        return
    if state.kind in effects.NO_EFFECT or state.owner_only:
        if words is not None:                   # its buttons run settle and undo, not this path
            work.notes.append(owner_only_reply(state, asked))
        return
    said = choice.answer
    passes = words.passes if words is not None else True    # a press is the owner's own
    evidence = words.evidence if words is not None else choice.label
    confidence = words.confidence if words is not None else 1.0
    if said == "accepted" and not passes:
        return
    pressed = (_pressed(work.session, source, card, question) if isinstance(source, Button)
               else None)
    rejection = words.rejection if words is not None else (
        "misread" if state.kind == "trial" else None)
    confirm: Callable[..., None] = (work.confirm if pressed is None
                                    else partial(work.confirm, pressed=pressed))
    found = work.index.get(record) if record else None
    if found is not None and state.kind in PINNED_KINDS and found.hash != hash:
        _close_stale(work, state, found, evidence)      # the owner answered an older version
        return
    if found is not None and state.kind in ("trial", "backlog"):
        if said == "accepted":
            confirm(record, found.hash, evidence, confidence, label="yes")
        elif said == "rejected":
            work.reject(found, evidence, confidence, rejection, pressed=pressed)
    text = said if said != "change" else f"change: {choice.change or evidence}"
    answers = (*state.answers, ClarifyAnswer(question or state.id, text, work.digest))
    answered = {a.question for a in answers}
    done = all(q.id in answered for q in state.questions) if state.questions else True
    state = dataclasses.replace(state, answers=answers, status="answered" if done else "open")
    work.cards[state.id] = state
    if done:
        work.closed.append(state.id)
    handler = effects.handler_for(state.kind)
    if handler is None:
        return
    result = handler(
        core=work.core, job=work.job, card=state, question=question,
        entry={"answer": said, "change": choice.change, "confidence": confidence,
               "evidence": evidence, "record": record, "hash": hash},
        message=work.message, digest=work.digest, accepted=said == "accepted" and passes,
        confirm=confirm, session=work.session, source=source)
    if isinstance(result, Applied):
        work.entries.extend(result.entries)
        for extra in result.cards:
            work.cards[extra.id] = extra
        work.closed.extend(result.closed)
        work.notes.extend(result.notes)
