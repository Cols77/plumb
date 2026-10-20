"""``plumb mod press``: one button the owner pressed on a drawn card (sp7-realign-sp8 C4-C6).

The press carries the session's key on stdin, the offer the card was drawn as and the index of
the button in that offer. Refused (exit 3, nothing written) under the agent session marker,
without a registered panel, without the key or with another key, and for an offer that was not
drawn in this session. Otherwise the press is logged (``card-press``, every button) and
answered through the one answer path (``understand.answer.apply_answer``, ``Button`` source):

- a record the card asks about that changed since it was drawn is left out and named: nothing is
  confirmed, the card is closed and the version it has now is shown as a fresh card;
- Confirm (an ``accepted`` choice) writes ``approval {by: owner, via: button, offer, card,
  question, key_digest, records: [{id, hash}]}`` at exactly the hash drawn;
- a ``rejected`` choice writes the rejection as a typed "no" would, ``by: owner, via: button``
  (on a trial card it is a misreading: plumb's reading is marked wrong and the record stays);
- Leave open sets the card ``left_open`` (it stops repeating at turn end until its record
  changes, DEC-034); Ask for a change sets it ``change_requested`` and the answer carries the
  text the mod puts in the message box (DEC-032). Neither writes an approval."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from plumb.contracts import CARD_PRESS, Choice
from plumb.mod import offers as offers_mod
from plumb.mod.session import Refused, check_key
from plumb.present import owner_text


class Unknown(LookupError):
    """The press names a button or a card that does not exist (nothing was written)."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _write(core: Any, session: str, applied: Any, closed_card: str | None) -> None:
    from plumb import log, stale
    from plumb.understand import cardstore

    closed = set(applied.closed) | ({closed_card} if closed_card else set())
    for card in applied.cards:
        if card.kind == "stale_link":
            stale.save_decision(core, session, card)
    if applied.cards or closed:
        replaced = {c.id for c in applied.cards}
        kept = [dataclasses.replace(c, status="closed") if c.id in closed else c
                for c in cardstore.own_cards(core.root, session) if c.id not in replaced]
        cardstore.save(core.root, session, [*kept, *applied.cards])
    for entry in applied.entries:
        kind = str(entry["kind"])
        core.log_append(log.stream_of(kind), kind, dict(entry["payload"]))


def _ids(entries: Any, kind: str) -> list[str]:
    return [str(r.get("id")) for e in entries if e["kind"] == kind
            for r in e["payload"].get("records") or () if isinstance(r, Mapping)]


def _quoted(core: Any, ids: list[str]) -> str:
    index = core.index()
    return ", ".join(f'"{index[i].title}"' if i in index else i for i in ids)


def _model_records(core: Any, ids: list[str]) -> str:
    index = core.index()
    return ", ".join(f"{i} '{index[i].title}'" if i in index else i for i in ids)


def press(core: Any, session: str, offer: str, index: int,
          payload: Mapping[str, Any], *, surface: str = "mod") -> dict[str, Any]:
    """Answer the button ``index`` of ``offer`` (see the module doc). Raises ``Refused``
    (exit 3) or ``Unknown`` (exit 1 or 2) with nothing written."""
    from plumb.understand import answer, cardstore

    if surface == "browser":
        from plumb.browser.session import check_key as browser_check_key
        digest = browser_check_key(core.root, session, payload, "press")
    elif surface == "mod":
        digest = check_key(core.root, session, payload, "press")
    else:
        raise Refused("unknown owner surface")
    drawn = offers_mod.load_offer(core.root, session, offer, surface=surface)
    if drawn is None:
        raise Refused("plumb mod press refused: no such card was drawn in this session")
    if surface == "browser" and drawn.get("key_digest") != digest:
        raise Refused("This offer belongs to an earlier browser registration; "
                      "redraw before answering")
    buttons = [b for b in drawn.get("buttons") or () if isinstance(b, Mapping)]
    if not 0 <= index < len(buttons):
        raise Unknown(f"plumb mod press: the card has no button {index}", 2)
    button = buttons[index]
    choice = Choice(label=str(button.get("label", "")),
                    answer=button.get("answer") if button.get("answer") in
                    ("accepted", "rejected", "change", "open") else "open",
                    change=None if button.get("change") is None else str(button["change"]))
    card_id, question = str(drawn["card"]), str(drawn.get("question") or "")
    record_id, shown_hash = drawn.get("record"), str(drawn.get("hash") or "")
    card = next((c for c in cardstore.load(core.root, session, open_only=False)
                 if c.id == card_id), None)
    built = offers_mod.turn_card(core.root, session, card_id) if card is None else None
    if card is None and built is None:
        raise Unknown("plumb mod press: that card no longer exists; nothing was written", 1)
    current_card = card or built
    if surface == "browser" and drawn.get("presentation") != offers_mod.presentation_digest(
            core, session, current_card):
        # Record drift still goes through the existing stale-record refusal/replacement path.
        record = core.index().get(str(record_id)) if record_id else None
        if not record_id or (record is not None and record.hash == shown_hash):
            raise Refused("The card changed since it was shown. Refresh it before answering.")
    if built is not None:
        return _press_turn_card(core, session, offer, index, choice, built, question,
                                record_id, shown_hash, digest, surface=surface,
                                request_id=str(payload.get("request_id") or ""))
    assert card is not None
    core.log_append("events", CARD_PRESS, {
        "session": session, "offer": offer, "card": card_id, "question": question,
        "choice": index, "answer": choice.answer, "label": choice.label,
        "record": record_id, "hash": shown_hash, "key_digest": digest,
        **({"surface": "browser", "request_id": payload.get("request_id")}
           if surface == "browser" else {}),
        # decided now, so a later edit of the record never turns a confirmed card blocked
        "stale": bool(record_id) and (core.index().get(str(record_id)) is None
                                      or core.index()[str(record_id)].hash != shown_hash)})
    result: dict[str, Any] = {
        "ok": True, "offer": offer, "card": card_id, "question": question, "choice": index,
        "label": choice.label, "answer": choice.answer, "status": card.status,
        "confirmed": [], "rejected": [], "left_out": [], "fresh_cards": [], "prefill": None,
        "line": "", "model_note": "", "notes": []}
    if card.status not in offers_mod.DRAWN:
        result["line"] = owner_text.PRESS_ALREADY.format(topic=card.topic)
        return result
    work = answer.Answering(core, session)
    work.open_cards[card.id] = card                     # a card left open can still be pressed
    current = work.index.get(str(record_id)) if record_id else None
    closed_card: str | None = None
    if record_id and (current is None or current.hash != shown_hash):
        title = current.title if current is not None else str(record_id)
        result["left_out"] = [{"id": record_id, "title": title,
                               "reason": "changed since it was shown"}]
        if current is not None:
            answer._close_stale(work, card, current)
        else:
            closed_card = card.id
        result["line"] = owner_text.PRESS_CHANGED_SINCE.format(title=title)
        result["model_note"] = owner_text.PRESS_MODEL_CHANGED.format(
            label=choice.label, records=_model_records(core, [str(record_id)]))
    else:
        answer.apply_answer(work, card=card_id, question=question, record=str(record_id or ""),
                            hash=shown_hash, choice=choice,
                            source=answer.Button(offer_id=offer, key_digest=digest,
                                                 surface=surface))
        if not answer.is_left(choice):     # SR-333 EX-5: a judge question studied in the room
            from plumb.understand import question as asked

            asked.answered_in_room(core, session, card_id, choice.label)
    applied = work.applied()
    _write(core, session, applied, closed_card)
    after = next((c for c in applied.cards if c.id == card_id), None)
    status = "closed" if (card_id in applied.closed or closed_card) else (
        after.status if after is not None else card.status)
    confirmed, rejected = _ids(applied.entries, "approval"), _ids(applied.entries, "rejection")
    result.update(status=status, confirmed=confirmed, rejected=rejected,
                  fresh_cards=[c.id for c in applied.cards if c.id != card_id],
                  notes=list(applied.notes))
    if result["left_out"]:
        return result
    topic = card.topic
    if confirmed:
        result["line"] = owner_text.PRESS_CONFIRMED.format(label=choice.label,
                                                          titles=_quoted(core, confirmed))
        result["model_note"] = owner_text.PRESS_MODEL_CONFIRMED.format(
            label=choice.label, records=_model_records(core, confirmed))
    elif rejected:
        # a trial No marks plumb's reading wrong (capture-error); the record stays (SR-124)
        misread = any(e["kind"] == "rejection" and e["payload"].get("reason") == "capture-error"
                      for e in applied.entries)
        line, note = ((owner_text.PRESS_MISREAD, owner_text.PRESS_MODEL_MISREAD) if misread
                      else (owner_text.PRESS_REJECTED, owner_text.PRESS_MODEL_REJECTED))
        result["line"] = line.format(label=choice.label, titles=_quoted(core, rejected))
        result["model_note"] = note.format(label=choice.label,
                                           records=_model_records(core, rejected))
    elif status == "left_open":
        result["line"] = owner_text.PRESS_LEFT_OPEN.format(topic=topic)
        result["model_note"] = owner_text.PRESS_MODEL_LEFT_OPEN.format(topic=topic)
    elif status == "change_requested":
        result["prefill"] = owner_text.PRESS_PREFILL.format(topic=topic)
        result["line"] = owner_text.PRESS_CHANGE.format(topic=topic)
        result["model_note"] = owner_text.PRESS_MODEL_CHANGE.format(topic=topic)
    else:
        result["line"] = (applied.notes[0] if applied.notes else
                          owner_text.PRESS_ANSWERED.format(label=choice.label, topic=topic))
        result["model_note"] = owner_text.PRESS_MODEL_ANSWERED.format(label=choice.label,
                                                                      topic=topic)
    return result


def conflict_take(card: Any, choice: Choice) -> str | None:
    """The side a press on a merge conflict card keeps (``ours``, ``theirs``, or ``combined``
    when one is proposed), None for any other card or button."""
    from plumb.understand import cards

    if card.kind != "conflict":
        return None
    return {cards.KEEP_THIS: "ours", cards.KEEP_OTHER: "theirs"}.get(
        choice.label, "combined" if choice.label == cards.BOTH and choice.answer == "accepted"
        else None)


def _press_turn_card(core: Any, session: str, offer: str, index: int, choice: Choice,
                     card: Any, question: str, record_id: Any, shown_hash: str,
                     digest: str, *, surface: str = "mod", request_id: str = ""
                     ) -> dict[str, Any]:
    """A press on a card the stop hook built (not in ``cards.json``): it offers only Leave open
    (DEC-034: kept in ``turn_left.json`` until a record it shows changes) and Ask for a change
    (the owner's next message says what; nothing is stored). Neither confirms anything."""
    from plumb.understand import answer, summary

    side = conflict_take(card, choice)
    if not answer.is_left(choice) and side is None:
        raise Unknown("plumb mod press: that button cannot answer this card", 2)
    def log_press() -> None:
        core.log_append("events", CARD_PRESS, {
            "session": session, "offer": offer, "card": card.id, "question": question,
            "choice": index, "answer": choice.answer, "label": choice.label,
            "record": record_id, "hash": shown_hash, "key_digest": digest,
            **({"surface": "browser", "request_id": request_id}
               if surface == "browser" else {})})

    if side is None:
        log_press()
    topic = card.topic
    result: dict[str, Any] = {
        "ok": True, "offer": offer, "card": card.id, "question": question, "choice": index,
        "label": choice.label, "answer": choice.answer, "status": card.status,
        "confirmed": [], "rejected": [], "left_out": [], "fresh_cards": [], "prefill": None,
        "line": "", "model_note": "", "notes": []}
    if side is not None and not answer.is_left(choice):
        from plumb.mergedriver import conflicts
        from plumb.understand import cards

        try:
            found = conflicts.find(core, card.id.removeprefix("conflict:"))
            if cards.conflict_card(core.index(), found).evidence != card.evidence:
                # the sides or the combined version are not what the owner was shown
                raise Unknown(owner_text.PRESS_CHANGED_SINCE.format(title=card.topic)
                              + " Nothing was written.", 1)
            conflicts.apply_choice(core, found, side, by="owner")
            log_press()     # logged once applied: a refused press answers nothing (SR-160)
        except conflicts.ConflictError as exc:
            raise Unknown(f"plumb mod press: {exc}; nothing was written", 1) from exc
        result.update(status="closed",
                      line=owner_text.PRESS_ANSWERED.format(label=choice.label, topic=topic),
                      model_note=owner_text.PRESS_MODEL_ANSWERED.format(label=choice.label,
                                                                        topic=topic))
    elif choice.answer == "open":
        summary.leave_turn_card(core.root, session, card)
        result.update(status="left_open",
                      line=owner_text.PRESS_LEFT_OPEN.format(topic=topic),
                      model_note=owner_text.PRESS_MODEL_LEFT_OPEN.format(topic=topic))
    else:
        result.update(status="change_requested",
                      prefill=owner_text.PRESS_PREFILL.format(topic=topic),
                      line=owner_text.PRESS_CHANGE.format(topic=topic),
                      model_note=owner_text.PRESS_MODEL_CHANGE.format(topic=topic))
    if choice.answer != "open":
        summary.clear_turn_left(core.root, session, card.id, result["status"])
    return result
