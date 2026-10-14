"""The end-of-turn summary of the understanding layer (JUDGE, SR-105).

``stop_parts`` gives the stop hook, in the order of SR-105:

1. what the owner confirmed by their words ("you said ...", READ's ``confirmation_lines``);
2. the cards: clarify, trial, goes beyond your words, contradicts, couldn't check, then the
   kinds the stop hook builds (a regression, a drift, a merge conflict, an early conflict), then
   the others (a record to look at, a stale link). Each is drawn in full (``fullcard``,
   SR-116). A stale card the agent left incomplete is not offered (SR-116 EX-3) and stays open;
   one line counts those. Nothing here resolves, expires or hides a card; only the owner's
   Leave open press stops a card repeating until its record changes (``_repeats_at_turn_end``,
   DEC-034).

plumb builds the facts; the agent words the suggested resolutions for the owner from them. The
turn's upkeep (``_upkeep``) runs first when the hook's budget allows. Nothing here confirms
anything."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import CardState, Choice, ClarifyQuestion, StopParts
from plumb.present import owner_text
from plumb.understand import cards as card_text
from plumb.understand import cardstore, files

UNDER_BUDGET_S = 0.35        # the upkeep (the log's cards, the offers) needs this much left
CALIBRATE_S = 0.9            # rerunning the calibration needs this much left


# --------------------------------------------------------------------------- what was told


class Told:
    """What the owner was already told in this session (``told.json``): the notices said once
    and the owner-words confirmations."""

    def __init__(self, root: Any, session: str, now: str) -> None:
        self.path = files.session_dir(root, session) / "told.json"
        raw = files.read_json(self.path)
        data = raw if isinstance(raw, Mapping) else {}
        self.since = str(data.get("since") or now)
        self.notices = set(str(d) for d in data.get("notices") or ())
        self.confirmed = set(str(d) for d in data.get("confirmed") or ())
        self.dirty = not data

    def save(self) -> None:
        if self.dirty:
            files.write_json_atomic(self.path, {"since": self.since,
                                                "notices": sorted(self.notices),
                                                "confirmed": sorted(self.confirmed)})


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# --------------------------------------------------------------------------- the parts


def _confirmations(core: Any, turn: Any, told: Told | None = None) -> tuple[str, ...]:
    """What the owner's words confirmed for this turn's message, then what they confirmed for
    an earlier message whose read finished after that turn ended (told once)."""
    try:
        from plumb.understand import read

        lines = [str(line) for line in read.confirmation_lines(core, turn)]  # READ's wording
    except (ImportError, AttributeError):
        return ()
    if told is None:
        return tuple(lines)
    digest = turn.get("prompt_digest") if isinstance(turn, Mapping) else turn
    index = core.index()
    for entry in core.events():
        payload = entry.payload
        if (entry.kind != "approval" or payload.get("by") != "owner-words"
                or entry.digest in told.confirmed):
            continue
        told.confirmed.add(entry.digest)
        told.dirty = True
        if payload.get("prompt_digest") == digest or entry.at < told.since:
            continue                      # this turn's own (above), or older than the session
        said = owner_text.CONFIRM_YOU_SAID.format(evidence=payload.get("evidence", ""))
        for record in payload.get("records") or ():
            item = index.get(str(record.get("id")))
            lines.append(f"{item.title}: {said}" if item is not None else said)
    return tuple(lines)


def _failure_cards(core: Any, session: str) -> list[CardState]:
    """A "couldn't check" card for each job that failed and has not succeeded since (SR-104
    EX-3): what was not done and that it will be tried again; the owner is asked
    whether to build without the check."""
    from pathlib import Path

    from plumb.understand import clarify, queue

    out: list[CardState] = []
    for result in queue.failures(core, session):
        raw = files.read_json(files.jobs_dir(core.root, session) / f"{result.job}.json")
        kind = str(raw.get("kind")) if isinstance(raw, Mapping) else ""
        message = ((raw.get("inputs") or {}).get("message") or {}) if isinstance(raw, Mapping) else {}
        if kind == "clarify" and any(c.id == clarify.couldnt_card_id(str(message.get("digest")))
                                     for c in cardstore.own_cards(Path(core.root), session)):
            continue                      # `plumb clarify` already drew this failure's card
        text = str(message.get("text") or "") if isinstance(message, Mapping) else ""
        topic = (clarify.TOPIC.format(date=result.started[:10], text=clarify._clipped(text))
                 if text.strip() else {"judge": owner_text.STEP_JUDGING_BACKLOG,
                                       "read": owner_text.STEP_READING}.get(
                                           kind, owner_text.STEP_CHECKING))
        options = (owner_text.GATE_WAIT, owner_text.GATE_BUILD_ANYWAY)
        out.append(CardState(
            id=f"couldnt_check:{result.job}", kind="couldnt_check", topic=topic,
            issue=owner_text.COULDNT_CHECK_ISSUE, resolutions=options,
            questions=(ClarifyQuestion(
                id=f"couldnt_check:{result.job}#1", text=clarify.COULDNT_QUESTION,
                resolutions=options, choices=(
                    Choice(owner_text.GATE_WAIT, "rejected",
                           consequence=owner_text.GATE_WAIT_NOTE),
                    Choice(owner_text.GATE_BUILD_ANYWAY, "accepted",
                           consequence=owner_text.GATE_BUILD_NOTE))),)))
    return out


def _labels_since_calibration(entries: Sequence[Any]) -> bool:
    """Whether an owner label (a trial answered, an owner-words confirmation, a rejection, an
    undo) came after the latest calibration from logged scores."""
    last = -1
    for position, entry in enumerate(entries):
        if entry.kind == "calibration" and entry.payload.get("source") == "logged":
            last = position
    return any(e.kind in ("trial", "rejection")
               or (e.kind == "approval" and e.payload.get("by") == "owner-words")
               or (e.kind == "revocation" and e.payload.get("by") == "undone")
               for e in entries[last + 1:])


def _upkeep(core: Any, session: str, recalibrate: bool) -> list[CardState]:
    """The turn's upkeep, from the logs alone (no model): rerun the calibration from the logged
    scores after an owner label, then top up the trial cards."""
    from plumb.understand import trial

    entries = core.events()
    if recalibrate and any(e.kind == "verdict" for e in entries) and _labels_since_calibration(
            entries):
        try:
            from plumb.capture import calibrate

            calibrate.calibrate(core)
        except Exception:  # noqa: BLE001 - upkeep never fails the turn
            pass
    return trial.top_up(core, session)


def stop_parts(ctx: Any, core: Any, turn: Any, *, extra: Sequence[CardState] = (),
               fresh: Sequence[CardState] = (), passing: Sequence[str] = (),
               shown: dict[str, str] | None = None) -> StopParts:
    """The two parts of the stop hook's summary (see the module docstring). Never raises
    for a part that cannot be made: that part is left out.

    ``extra`` are the cards the stop hook builds from this turn's facts (a regression, a
    changed acceptance test); they are kept in the session's ``turn_cards.json`` and drawn at
    every turn end until they are moot (``_moot``). ``fresh`` are drawn this turn only
    because the stop hook rebuilds them each turn while they hold (a merge conflict, an early
    conflict). ``passing`` are the test nodes that pass now (a regression card of one is
    moot). Every card is drawn in full (``fullcard``, SR-116); ``shown`` is filled with
    ``{record id: version shown}`` of every record a drawn card showed (the stated set's
    ``shown``)."""
    session = str(getattr(ctx, "session_id", "") or files.CLI_SESSION)
    turn = turn if isinstance(turn, Mapping) else {}
    started = float(turn.get("turn_start") or 0) or time.time()
    deadline = getattr(ctx, "deadline", None)
    roomy = deadline is None or deadline.remaining_s() > UNDER_BUDGET_S
    told = Told(core.root, session, _iso(started))
    confirmations = _confirmations(core, turn, told)
    told.save()
    upkeep: list[CardState] = []
    if roomy:
        try:
            upkeep = _upkeep(core, session,
                             deadline is None or deadline.remaining_s() > CALIBRATE_S)
        except Exception:  # noqa: BLE001 - the upkeep never costs the owner their summary
            pass
        try:
            from plumb.understand import backlog

            backlog.resume(core, session)    # a pass a failure interrupted goes on (spec 8)
        except Exception:  # noqa: BLE001 - queueing never costs the owner their summary
            pass
    rendered: tuple[str, ...] = ()
    try:
        rendered = tuple(_cards(core, session, upkeep, int(started), deadline,
                                extra=extra, fresh=fresh, passing=set(passing), shown=shown))
    except Exception:  # noqa: BLE001 - a card that cannot be made is left out, not fatal
        rendered = ()
    return StopParts(confirmations=confirmations, cards=rendered)


# --------------------------------------------------------------------------- the cards

TURN_CARDS = "turn_cards.json"   # the cards the stop hook built, kept while they hold
DRAWN = "drawn.json"             # every card drawn at the last turn end, with its full content
TURN_LEFT = "turn_left.json"     # the stop hook's cards the owner left open, with what they showed
WAITING = "cards_waiting.json"   # what the next prompt tells the agent (SR-116 EX-4)
DRAW_MIN_S = 0.08                # a card's full content needs about this much of the budget


def _held(core: Any, session: str) -> list[CardState]:
    raw = files.read_json(files.session_dir(core.root, session) / TURN_CARDS)
    out = []
    for item in raw if isinstance(raw, list) else ():
        if isinstance(item, Mapping) and isinstance(item.get("card"), Mapping):
            out.append(cardstore.card_from_json(item["card"]))
    return out


def _keep(core: Any, session: str, held: Sequence[CardState]) -> None:
    files.write_json_atomic(files.session_dir(core.root, session) / TURN_CARDS, [
        {"card": cardstore.card_to_json(c)} for c in held])


def _moot(core: Any, card: CardState, statuses: Mapping[str, Any],
          passing: set[str]) -> CardState | None:
    """The card as it still holds, or None when its question no longer stands: a decision
    confirmed since needs no card, a regression whose test passes again is over. Nothing the
    owner has to answer is dropped here."""
    index = core.index()

    def done(record_id: str | None) -> bool:
        if not record_id or record_id not in index:
            return True
        state = statuses.get(record_id)
        return state is not None and (state.confirmation == "confirmed"
                                      or state.superseded_by is not None)

    if card.kind in ("decision", "early_conflict", "test_changed"):
        return None if all(done(q.record) for q in card.questions) else card
    if card.kind == "regression":
        node = card.evidence.split(" ", 1)[0]
        return None if node in passing or any(
            q.text in passing for q in card.questions) else card
    return card


def _repeats_at_turn_end(card: CardState) -> bool:
    """Whether a card is drawn at this turn end (DEC-034): every card that still asks the owner
    (``cardstore.AWAITING``: open, or waiting for the owner's words after Ask for a change)
    shows at the end of every turn. A card the owner pressed Leave open on (``left_open``,
    written by ``plumb mod press``) does not repeat here until a record it asks about changes
    (``mod.offers.reopen_changed`` reopens it first); it stays listed under what awaits the
    owner in the band and the pane (``mod.offers.DRAWN``). That press is the only thing that
    makes this False; nothing here resolves, expires or hides a card."""
    return card.status in cardstore.AWAITING


def _turn_cards(core: Any, session: str, extra: Sequence[CardState],
                passing: set[str]) -> list[CardState]:
    """The cards the stop hook built, this turn's and the earlier turns' that still hold;
    written back so they are drawn again at the next turn end."""
    held = {c.id: c for c in _held(core, session)}
    held.update({card.id: card for card in extra})
    wanted = sorted({q.record for c in held.values() for q in c.questions if q.record})
    statuses = core.status(wanted) if wanted else {}
    out = [still for card in held.values()
           if (still := _moot(core, card, statuses, passing)) is not None]
    if out or held:
        _keep(core, session, out)
    return out


def _cards(core: Any, session: str, upkeep: Sequence[CardState], stamp: int,
           deadline: Any, *, extra: Sequence[CardState] = (),
           fresh: Sequence[CardState] = (), passing: set[str] | None = None,
           shown: dict[str, str] | None = None) -> list[str]:
    from plumb import stale
    from plumb.understand import fullcard

    if upkeep:
        own = cardstore.own_cards(core.root, session)
        have = {c.id for c in own}
        add = [c for c in upkeep if c.id not in have]
        if add:
            cardstore.save(core.root, session, [*own, *add])
    from plumb.mod.offers import reopen_changed

    reopen_changed(core, session)       # DEC-034: a card left open returns once it changed
    held = cardstore.states(core, session)
    open_cards = [c for c in cardstore.load(core.root, session, open_only=False)
                  if _repeats_at_turn_end(c) and held.get(c.id, ("",))[0] != "processing"]
    open_cards.extend(_failure_cards(core, session))
    built = _turn_cards(core, session, extra, passing or set())
    seen = {c.id for c in open_cards}
    turn_built = [*(c for c in built if c.id not in seen),
                  *(c for c in fresh if c.id not in seen)]
    turn_ids = {c.id for c in turn_built}
    left = _turn_left_now(core, session, turn_built)
    every = [*open_cards, *(c for c in turn_built if c.id not in left)]
    kept: list[dict[str, Any]] = []
    for card in turn_built:
        if card.id in left:     # DEC-034: listed as awaiting, not drawn again until it changes
            kept.append(_drawn_entry(core, session, card, "left_open", turn_built=True))
    entries = {f"stale:{e.get('link', '')}": e for e in stale.read_cards(core.root, session)
               if e.get("status", "open") == "open"}
    out: list[str] = []
    drawn: list[str] = []
    drawn_ids: list[str] = []
    incomplete = 0
    late: list[str] = []
    for card in sorted(every, key=card_text.kind_rank):
        entry = entries.get(card.id) if card.kind == "stale_link" else None
        if entry is not None and not stale.card_complete(entry):
            incomplete += 1              # SR-116 EX-3: not offered until the agent fills it
            continue
        if entry is not None and deadline is not None and \
                deadline.remaining_s() < DRAW_MIN_S:
            # the diff of a stale link reads git: past the budget the card is named, never
            # cut silently, and drawn in full at the next turn end (the others read records)
            late.append(card.topic)
            continue
        if entry is not None:
            item = fullcard.stale_content(core, entry, session=session)
        else:
            item = fullcard.content(core, card)
        out.append(fullcard.render(item))
        drawn.append(card.topic)
        drawn_ids.append(card.id)
        kept.append({"card": cardstore.card_to_json(card), "content": item,
                     "turn_built": card.id in turn_ids})
        if shown is not None:
            for question in card.questions:
                if question.record:
                    shown.setdefault(question.record, question.hash)
    if late:
        out.append(owner_text.FULL_NOT_DRAWN.format(
            n=len(late), topics="; ".join(f'"{t}"' for t in late)))
    if incomplete:
        out.append(owner_text.FULL_INCOMPLETE.format(n=incomplete))
    _waiting(core, session, drawn, drawn_ids)
    # an answered turn-built card (a resolved conflict) stays listed, so the turn line and the
    # pane's Done list still know it after this rewrite
    answered = {p.get("card") for p in cardstore.answer_presses(core, session)}
    have = {e["card"].get("id") for e in kept}
    kept += [e for e in read_drawn(core.root, session) if e.get("turn_built")
             and e["card"].get("id") in answered and e["card"].get("id") not in have]
    files.write_json_atomic(files.session_dir(core.root, session) / DRAWN, kept)
    return out


def _drawn_entry(core: Any, session: str, card: CardState, status: str, *,
                 turn_built: bool) -> dict[str, Any]:
    from plumb.understand import fullcard

    card = dataclasses.replace(card, status=status)  # type: ignore[arg-type]
    item = fullcard.content(core, card)
    return {"card": cardstore.card_to_json(card), "content": item, "turn_built": turn_built}


def read_drawn(root: Any, session: str) -> list[dict[str, Any]]:
    """Every card drawn at the last turn end (``{card, content, turn_built}``): the cards the
    owner reads, each with its full content (SR-116), and the stop hook's cards the owner left
    open (status ``left_open``). What ``present.json`` and ``plumb mod draw`` carry."""
    raw = files.read_json(files.session_dir(root, session) / DRAWN)
    return [dict(e) for e in raw if isinstance(e, Mapping) and isinstance(e.get("card"), Mapping)
            ] if isinstance(raw, list) else []


def _shows(card: CardState) -> dict[str, str]:
    return {str(q.record): q.hash for q in card.questions if q.record}


def leave_turn_card(root: Any, session: str, card: CardState) -> None:
    """DEC-034 for a card the stop hook builds (a regression, a decision, a conflict, the
    records the turn proposed): it is not in ``cards.json``, so the owner's Leave open is kept
    here with the versions it showed; it is not drawn again until one of them changes."""
    path = files.session_dir(root, session) / TURN_LEFT
    raw = files.read_json(path)
    held = dict(raw) if isinstance(raw, Mapping) else {}
    held[card.id] = _shows(card)
    files.write_json_atomic(path, held)


def turn_left(root: Any, session: str) -> dict[str, Any]:
    raw = files.read_json(files.session_dir(root, session) / TURN_LEFT)
    return dict(raw) if isinstance(raw, Mapping) else {}


def _turn_left_now(core: Any, session: str, built: Sequence[CardState]) -> set[str]:
    """The stop hook's cards still left open this turn end: the owner pressed Leave open and
    no record the card shows changed since (a changed one returns, DEC-034). Entries for cards
    that no longer hold are dropped."""
    held = turn_left(core.root, session)
    if not held:
        return set()
    index = core.index()
    by_id = {c.id: c for c in built}
    keep: dict[str, Any] = {}
    for card_id, shows in held.items():
        card = by_id.get(card_id)
        if card is None or not isinstance(shows, Mapping):
            continue
        if any(rid not in index or index[rid].hash != h for rid, h in shows.items()) or                 _shows(card) != dict(shows):
            continue
        keep[card_id] = dict(shows)
    if keep != held:
        files.write_json_atomic(files.session_dir(core.root, session) / TURN_LEFT, keep)
    return set(keep)


def _waiting(core: Any, session: str, topics: Sequence[str], ids: Sequence[str] = ()) -> None:
    """What the next prompt tells the agent (SR-116 EX-4): how many cards the owner was shown
    and their topics, so the reply names them in one line and never restates them."""
    path = files.session_dir(core.root, session) / WAITING
    if not topics:
        try:
            path.unlink()
        except OSError:
            pass
        return
    files.write_json_atomic(path, {"n": len(topics), "topics": list(topics),
                                 "ids": list(ids)})


def waiting_line(root: Any, session: str, core: Any = None) -> str | None:
    """The agent's one line about the cards waiting for the owner (SR-116 EX-4), or None.
    A card the owner has answered since (SR-160) is no longer named."""
    raw = files.read_json(files.session_dir(root, session) / WAITING)
    if not isinstance(raw, Mapping) or not raw.get("n"):
        return None
    topics = [str(t) for t in raw.get("topics") or ()]
    ids = [str(i) for i in raw.get("ids") or ()]
    if core is not None and len(ids) == len(topics):
        held = cardstore.states(core, session)
        topics = [t for t, i in zip(topics, ids) if held.get(i, ("waiting",))[0] == "waiting"]
        if not topics:
            return None
    named = "; ".join(f'"{t}"' for t in topics[:5]) + (
        f" and {len(topics) - 5} more" if len(topics) > 5 else "")
    return owner_text.CARDS_WAITING_AGENT.format(n=len(topics), topics=named)
