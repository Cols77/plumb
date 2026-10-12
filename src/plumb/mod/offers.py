"""The cards the mod draws, and the offers recorded when they are drawn (sp7-realign-sp8 C3, C4).

Each drawn card question carries one offer: ``offer_id = digest(card id, question id, record
hash)`` (``files.digest_of``; a card with no question offers its card as question ``""``) and
its buttons: the question's suggested choices in order (the recommended one first), then always
**Ask for a change** and **Leave open**. The press names the offer and the button's index.

An offer is recorded once, when it is first drawn: ``.plumb/session/<s>/offers/<hex>.json``
(what the press reads: the card, question, record and hash shown, the buttons, ``drawn_at``) and
an ``offer`` log entry (what the re-check of a button approval reads: the session folder is not
committed, the log is)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import CardState, Choice, ClarifyQuestion
from plumb.present import owner_text
from plumb.understand import cardstore, files

OFFER_KIND = "offer"
# what the mod draws: the awaiting cards, and the ones left open (listed, not repeated)
DRAWN = (*cardstore.AWAITING, "left_open")


def offer_id(card: str, question: str, record_hash: str) -> str:
    return files.digest_of([card, question, record_hash])


def offers_dir(root: Path, session: str) -> Path:
    return files.session_dir(root, session) / "offers"


def offer_path(root: Path, session: str, offer: str) -> Path:
    name = offer.removeprefix("sha256:")
    if not name or not all(c in "0123456789abcdef" for c in name):
        name = "-"
    return offers_dir(root, session) / f"{name}.json"


def load_offer(root: Path, session: str, offer: str) -> Mapping[str, Any] | None:
    data = files.read_json(offer_path(root, session, offer))
    if not isinstance(data, Mapping) or data.get("offer_id") != offer \
            or data.get("session") != session:
        return None
    return data


def buttons(card: CardState, question: ClarifyQuestion | None) -> tuple[Choice, ...]:
    """The buttons of one card question, in order: its choices, then Ask for a change and
    Leave open (C3)."""
    from plumb.understand.cards import choices_for

    resolutions = tuple(question.resolutions if question is not None else ()) \
        or card.resolutions
    chosen = (question.choices if question is not None else ()) \
        or choices_for(card.kind, resolutions)
    return (*chosen, Choice(owner_text.BUTTON_ASK_CHANGE, "change", None),
            Choice(owner_text.BUTTON_LEAVE_OPEN, "open", None))


def reopen_changed(core: Any, session: str) -> list[str]:
    """DEC-034: a card left open comes back (``open``) once a record it asks about changed
    since it was drawn. Returns the reopened card ids."""
    own = cardstore.own_cards(core.root, session)
    index = core.index()
    reopened: list[str] = []
    out: list[CardState] = []
    for card in own:
        if card.status == "left_open" and any(
                q.record and q.hash and (q.record not in index or index[q.record].hash != q.hash)
                for q in card.questions):
            card = dataclasses.replace(card, status="open")
            reopened.append(card.id)
        out.append(card)
    if reopened:
        cardstore.save(core.root, session, out)
    return reopened


def _button_json(n: int, choice: Choice) -> dict[str, Any]:
    return {"index": n, **files.choice_to_json(choice)}


def _record_offer(core: Any, session: str, data: Mapping[str, Any]) -> None:
    path = offer_path(core.root, session, str(data["offer_id"]))
    if isinstance(files.read_json(path), Mapping):
        return                                          # drawn before: the first draw stands
    files.write_json_atomic(path, dict(data))
    core.log_append("events", OFFER_KIND, {
        "session": session, "offer": data["offer_id"], "card": data["card"],
        "question": data["question"], "record": data["record"], "hash": data["hash"],
        "key_digest": data["key_digest"], "drawn_at": data["drawn_at"],
        "buttons": [{"label": b["label"], "answer": b["answer"]} for b in data["buttons"]]})


def content_for(core: Any, session: str, card: CardState,
                change: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """SR-116: the card's full content as the end-of-turn text draws it (``understand.fullcard``,
    the same dict for every kind: the record as it now reads, the change with its evidence, the
    owner's words, each option with what it does and leaves undone, why the recommended one).
    None when it cannot be made (the card is still drawn from its own fields)."""
    try:
        from plumb.understand import fullcard

        if card.kind != "stale_link":
            return fullcard.content(core, card, session=session, change=change)
        from plumb import stale

        link = card.id.removeprefix("stale:")
        for entry in stale.read_cards(core.root, session):
            if str(entry.get("link") or "") == link:
                return fullcard.stale_content(core, entry, session=session)
    except Exception:  # noqa: BLE001 - the card is still drawn from its own fields
        return None
    return None


def turn_buttons() -> tuple[Choice, ...]:
    """The buttons of a card the stop hook builds (a regression, a decision, a conflict, an
    early conflict, a drift, the records the turn proposed): it is not in ``cards.json`` and no
    press can apply its options, so it offers Ask for a change and Leave open; its options are
    in its content, for the owner to answer in words."""
    return (Choice(owner_text.BUTTON_ASK_CHANGE, "change", None),
            Choice(owner_text.BUTTON_LEAVE_OPEN, "open", None))


def turn_card(root: Path, session: str, card_id: str) -> CardState | None:
    """A card the stop hook built and drew at the last turn end, by id (None when it was not)."""
    from plumb.understand import summary

    for entry in summary.read_drawn(root, session):
        if entry.get("turn_built") and entry["card"].get("id") == card_id:
            return cardstore.card_from_json(entry["card"])
    return None


def _offers_of(core: Any, session: str, digest: str, stamp: str, card: CardState,
               turn_built: bool) -> list[dict[str, Any]]:
    questions: Sequence[ClarifyQuestion | None] = list(card.questions) or [None]
    offers: list[dict[str, Any]] = []
    for question in questions:
        qid = question.id if question is not None else ""
        record = question.record if question is not None else None
        record_hash = question.hash if question is not None else ""
        offer = offer_id(card.id, qid, record_hash)
        pressable = turn_buttons() if turn_built else buttons(card, question)
        data = {"offer_id": offer, "session": session, "card": card.id, "question": qid,
                "record": record, "hash": record_hash, "key_digest": digest,
                "drawn_at": stamp,
                "buttons": [_button_json(n, c) for n, c in enumerate(pressable)]}
        _record_offer(core, session, data)
        held = load_offer(core.root, session, offer) or data
        offers.append({k: held[k] for k in ("offer_id", "question", "record", "hash",
                                              "buttons", "drawn_at")})
    return offers


def unanswered(card: CardState) -> CardState:
    """A trial batch without the questions already answered (the owner answers it in part,
    one record at a time): an answered record is not offered again (SR-124, INT-032 (2)).
    Every other kind of card keeps all its questions: no record says otherwise for them."""
    answered = {a.question for a in card.answers}
    if card.kind != "trial" or len(card.questions) < 2 or not answered:
        return card
    left = tuple(q for q in card.questions if q.id not in answered)
    return dataclasses.replace(card, questions=left) if left else card


def drawn_cards(core: Any, session: str, digest: str) -> list[dict[str, Any]]:
    """The cards the mod draws for ``session`` (as ``cards.json`` holds them, never cut: the mod
    folds a long ``evidence`` by its ``evidence_size``), then the cards the stop hook built and
    drew at the last turn end (``summary.read_drawn``), each with its full content (SR-116, the
    same as the end-of-turn text) and each question with its offer and buttons (a question
    already answered is left out, ``unanswered``); every offer is recorded the first time it
    is drawn."""
    from plumb.mod.session import now
    from plumb.understand import summary

    reopen_changed(core, session)
    stamp = now()
    out: list[dict[str, Any]] = []
    have: set[str] = set()
    for card in cardstore.load(core.root, session, open_only=False):
        have.add(card.id)
        if card.status not in DRAWN:
            continue
        card = unanswered(card)
        out.append({**cardstore.card_to_json(card), "evidence_size": len(card.evidence),
                    "repeats": card.status in cardstore.AWAITING,
                    "offers": _offers_of(core, session, digest, stamp, card, False),
                    "content": content_for(core, session, card)})
    left = summary.turn_left(core.root, session)
    for entry in summary.read_drawn(core.root, session):
        if not entry.get("turn_built"):
            continue
        card = cardstore.card_from_json(entry["card"])
        if card.id in have:
            continue
        have.add(card.id)
        if card.id in left:
            card = dataclasses.replace(card, status="left_open")
        content = entry.get("content")
        out.append({**cardstore.card_to_json(card), "evidence_size": len(card.evidence),
                    "repeats": card.status in cardstore.AWAITING,
                    "offers": _offers_of(core, session, digest, stamp, card, True),
                    "content": dict(content) if isinstance(content, Mapping) else None})
    return out
