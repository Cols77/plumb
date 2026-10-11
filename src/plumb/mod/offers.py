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


def content_for(core: Any, session: str, card: CardState) -> dict[str, Any] | None:
    """SR-116: what the owner needs to choose that plumb derives each time the card is shown
    (the record as it now reads, the change with its evidence, the owner's words, each
    option's consequence, why the recommended one), as ``understand.cardcontent`` builds it for
    a stale-link card; None where that builder is absent or the card carries its parts in its
    own fields. The panel draws either form."""
    if card.kind != "stale_link":
        return None
    try:
        import importlib

        cardcontent = importlib.import_module("plumb.understand.cardcontent")
        from plumb import stale
    except ImportError:
        return None
    link = card.id.removeprefix("stale:")
    for entry in stale.read_cards(core.root, session):
        if str(entry.get("link") or "") == link:
            try:
                content = cardcontent.card_content(core, entry, session=session)
            except Exception:  # noqa: BLE001 - the card is still drawn from its own fields
                return None
            return content if isinstance(content, dict) else None
    return None


def drawn_cards(core: Any, session: str, digest: str) -> list[dict[str, Any]]:
    """The cards the mod draws for ``session`` (as ``cards.json`` holds them, never cut: the mod
    folds a long ``evidence`` by its ``evidence_size``), each question with its offer and
    buttons; every offer is recorded the first time it is drawn."""
    from plumb.mod.session import now

    reopen_changed(core, session)
    stamp = now()
    out: list[dict[str, Any]] = []
    for card in cardstore.load(core.root, session, open_only=False):
        if card.status not in DRAWN:
            continue
        questions: Sequence[ClarifyQuestion | None] = list(card.questions) or [None]
        offers: list[dict[str, Any]] = []
        for question in questions:
            qid = question.id if question is not None else ""
            record = question.record if question is not None else None
            record_hash = question.hash if question is not None else ""
            offer = offer_id(card.id, qid, record_hash)
            data = {"offer_id": offer, "session": session, "card": card.id, "question": qid,
                    "record": record, "hash": record_hash, "key_digest": digest,
                    "drawn_at": stamp,
                    "buttons": [_button_json(n, c)
                                for n, c in enumerate(buttons(card, question))]}
            _record_offer(core, session, data)
            held = load_offer(core.root, session, offer) or data
            offers.append({k: held[k] for k in ("offer_id", "question", "record", "hash",
                                                  "buttons", "drawn_at")})
        out.append({**cardstore.card_to_json(card), "evidence_size": len(card.evidence),
                    "repeats": card.status in cardstore.AWAITING, "offers": offers,
                    "content": content_for(core, session, card)})
    return out
