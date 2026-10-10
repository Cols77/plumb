"""The trial (JUDGE, SR-106). J1 form: one card per waiting record."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from plumb.contracts import Applied, CardState, ClarifyQuestion
from plumb.present import owner_text
from plumb.understand import cards, settle


def cards_for(core: Any, session: str, waiting: Sequence[settle.Waiting]) -> list[CardState]:
    out: list[CardState] = []
    for held in waiting:
        record = held.item.record
        issue = owner_text.CONFIRM_ISSUE
        cid = cards.card_id("trial", record.id, record.hash)
        out.append(CardState(
            id=cid, kind="trial", topic=record.title, issue=issue,
            evidence=cards.words_of(held.item.premise),
            resolutions=(owner_text.TRIAL_YES, owner_text.TRIAL_NO),
            questions=(ClarifyQuestion(id=f"{cid}#1", text=record.title,
                                       resolutions=(owner_text.TRIAL_YES, owner_text.TRIAL_NO),
                                       record=record.id),)))
    return out


def effect(**_: Any) -> Applied | None:
    return None
