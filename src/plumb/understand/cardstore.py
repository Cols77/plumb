"""The open cards of a session: ``cards.json`` (this module is its one writer, frozen in phase
C) plus, read-only, STALE's ``stale_cards.json`` as ``stale_link`` cards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import CARD_STATUSES, CardState, ClarifyAnswer, ClarifyQuestion, Present
from plumb.understand import files


def card_to_json(card: CardState) -> dict[str, Any]:
    return {"id": card.id, "kind": card.kind, "topic": card.topic, "issue": card.issue,
            "evidence": card.evidence, "resolutions": list(card.resolutions),
            "questions": [files.question_to_json(q) for q in card.questions],
            "status": card.status, "answers": [files.answer_to_json(a) for a in card.answers],
            "owner_only": card.owner_only, "turn": card.turn}


def card_from_json(data: Mapping[str, Any]) -> CardState:
    status = data.get("status")
    return CardState(
        id=str(data.get("id", "")), kind=str(data.get("kind", "clarify")),
        topic=str(data.get("topic", "")), issue=str(data.get("issue", "")),
        evidence=str(data.get("evidence", "")),
        resolutions=tuple(str(r) for r in data.get("resolutions") or ()),
        questions=tuple(ClarifyQuestion(
            id=str(q.get("id", "")), text=str(q.get("text", "")),
            resolutions=tuple(str(r) for r in q.get("resolutions") or ()),
            record=q.get("record"), hash=str(q.get("hash") or ""),
            choices=tuple(files.choice_from_json(c) for c in q.get("choices") or ()
                          if isinstance(c, Mapping)))
            for q in data.get("questions") or () if isinstance(q, Mapping)),
        status=status if status in CARD_STATUSES else "open",
        answers=tuple(ClarifyAnswer(str(a.get("question", "")), str(a.get("answer", "")),
                                    str(a.get("message_digest", "")))
                      for a in data.get("answers") or () if isinstance(a, Mapping)),
        owner_only=bool(data.get("owner_only")), turn=int(data.get("turn") or 0))


def own_cards(root: Path, session: str) -> list[CardState]:
    raw = files.read_json(files.cards_path(root, session))
    items = raw.get("cards") if isinstance(raw, Mapping) else raw
    return [card_from_json(c) for c in items or () if isinstance(c, Mapping)]


def stale_cards(root: Path, session: str) -> list[CardState]:
    """The open entries of ``stale_cards.json`` (``{link, record, path, topic, issue,
    options, recommended, turn, status}``) as ``stale_link`` cards: same topic, issue and
    resolutions, the recommended one first. Never written here."""
    raw = files.read_json(files.stale_cards_path(root, session))
    out: list[CardState] = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, Mapping) or item.get("status", "open") != "open":
            continue
        options = [str(o) for o in item.get("options") or ()]
        try:
            first = int(item.get("recommended") or 0)
        except (TypeError, ValueError):
            first = 0
        if 0 < first < len(options):
            options.insert(0, options.pop(first))
        out.append(CardState(
            id=f"stale:{item.get('link', '')}", kind="stale_link",
            topic=str(item.get("topic", "")), issue=str(item.get("issue", "")),
            evidence=str(item.get("path", "")), resolutions=tuple(options), status="open",
            turn=int(item.get("turn") or 0)))
    return out


def load(root: Path, session: str, *, open_only: bool = True) -> list[CardState]:
    """The session's cards: its own, then the stale-link ones."""
    cards = [*own_cards(root, session), *stale_cards(root, session)]
    return [c for c in cards if c.status == "open"] if open_only else cards


def save(root: Path, session: str, cards: Sequence[CardState]) -> None:
    """Write the session's own cards (stale-link cards are STALE's and never written)."""
    files.write_json_atomic(files.cards_path(root, session),
                            [card_to_json(c) for c in cards if c.kind != "stale_link"])


def present_to_json(present: Present) -> dict[str, Any]:
    """The shape of ``present.json`` (sp7-realign-sp8 C7): ``{turn, confirmations, settled,
    cards}``, the cards as ``cards.json`` holds them."""
    return {"turn": present.turn, "confirmations": list(present.confirmations),
            "settled": list(present.settled), "cards": [card_to_json(c) for c in present.cards]}


def present_from_json(data: Any) -> Present:
    if not isinstance(data, Mapping):
        return Present()
    return Present(turn=int(data.get("turn") or 0),
                   confirmations=tuple(str(c) for c in data.get("confirmations") or ()),
                   settled=tuple(str(s) for s in data.get("settled") or ()),
                   cards=tuple(card_from_json(c) for c in data.get("cards") or ()
                               if isinstance(c, Mapping)))
