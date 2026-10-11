"""The end-of-turn summary of the understanding layer (JUDGE, SR-105).

``stop_parts`` gives the stop hook, in the order of SR-105:

1. what the owner confirmed by their words ("you said ...", READ's ``confirmation_lines``);
2. one settled line, "Settled from your words: <title> (Undo); <title> (Undo)", with the notices
   that are said once (settling switched itself on for requirements);
3. the cards: clarify, trial batch, backlog feature, goes beyond your words, contradicts,
   couldn't check, then the kinds the stop hook builds (a regression, a drift, a merge
   conflict, an early conflict, a decision that matters, the records the turn proposed, one
   card per feature), then the others (a record to look at, the offer to settle intents, a
   stale link). Each is drawn in full (``fullcard``, SR-116): the record as it now reads, the
   change with its evidence (a long diff folded with its size, never cut), the owner's words,
   each option with what it does and leaves undone, and why the first. A stale card the agent
   left incomplete is not offered (SR-116 EX-3) and stays open; one line counts those.
   Nothing here resolves, expires or hides a card (``_repeats_at_turn_end``: slice 4's Leave
   open is the hook point).

plumb builds the facts; the agent words the suggested resolutions for the owner from them. The
turn's upkeep (``settle.refresh``) runs first when the hook's budget allows; the settled line is
cheap and always comes. Nothing here confirms anything."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import CardState, ClarifyQuestion, StopParts
from plumb.present import owner_text
from plumb.understand import cards as card_text
from plumb.understand import cardstore, files, settle

UNDER_BUDGET_S = 0.35        # the upkeep (the log's cards, the offers) needs this much left
CALIBRATE_S = 0.9            # rerunning the calibration needs this much left


# --------------------------------------------------------------------------- what was told


class Told:
    """What the owner was already told in this session (``told.json``): the settled approvals
    their line named, the notices said once. Settled approvals from before the session's
    first summary are not news."""

    def __init__(self, root: Any, session: str, now: str) -> None:
        self.path = files.session_dir(root, session) / "told.json"
        raw = files.read_json(self.path)
        data = raw if isinstance(raw, Mapping) else {}
        self.since = str(data.get("since") or now)
        self.settled = set(str(d) for d in data.get("settled") or ())
        self.notices = set(str(d) for d in data.get("notices") or ())
        self.confirmed = set(str(d) for d in data.get("confirmed") or ())
        self.dirty = not data

    def save(self) -> None:
        if self.dirty:
            files.write_json_atomic(self.path, {"since": self.since,
                                                "settled": sorted(self.settled),
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


def settled_line(core: Any, told: Told) -> tuple[list[str], list[str]]:
    """``(titles, digests)`` of the settled approvals not yet told that still stand."""
    index = core.index()
    fresh: list[tuple[Any, list[str]]] = []
    for entry in core.events():
        if entry.kind != "approval" or entry.payload.get("by") != "settled" \
                or entry.digest in told.settled or entry.at < told.since:
            continue
        ids = [str(r.get("id")) for r in entry.payload.get("records") or ()
               if isinstance(r, Mapping) and str(r.get("id")) in index]
        fresh.append((entry, ids))
    if not fresh:
        return [], []
    statuses = core.status(sorted({i for _, ids in fresh for i in ids}))
    titles: list[str] = []
    digests: list[str] = []
    for entry, ids in fresh:
        digests.append(entry.digest)
        for record_id in ids:
            state = statuses.get(record_id)
            if state is not None and state.settled and index[record_id].title not in titles:
                titles.append(index[record_id].title)
    return titles, digests


def _failure_cards(core: Any, session: str) -> list[CardState]:
    """A "couldn't check" card for each job that failed and has not succeeded since (SR-104
    EX-3): what was not done and that it will be tried again; a clarify job that failed asks
    whether to build without the check."""
    from plumb.understand import queue

    out: list[CardState] = []
    for result in queue.failures(core, session):
        raw = files.read_json(files.jobs_dir(core.root, session) / f"{result.job}.json")
        kind = str(raw.get("kind")) if isinstance(raw, Mapping) else ""
        step = result.error.step if result.error is not None else "run"
        if kind == "clarify":
            topic, options = (owner_text.STEP_CHECKING,
                              (owner_text.GATE_BUILD_ANYWAY, owner_text.GATE_WAIT))
        else:
            topic = {"judge": owner_text.STEP_JUDGING_BACKLOG, "read": owner_text.STEP_READING
                     }.get(kind, owner_text.STEP_CHECKING)
            options = ()
        out.append(CardState(
            id=f"couldnt_check:{result.job}", kind="couldnt_check", topic=topic,
            issue=owner_text.COULDNT_CHECK_ISSUE.format(step=step), resolutions=options,
            questions=(ClarifyQuestion(id=f"couldnt_check:{result.job}#1",
                                       text=owner_text.COULDNT_CHECK_ISSUE.format(step=step),
                                       resolutions=options,
                                       choices=card_text.choices_for("couldnt_check",
                                                                     options)),)
            if options else ()))
    return out


def _offered(card: CardState, shown: int) -> bool:
    return card.kind != "backlog" or card.turn == shown


def _meter(core: Any, session: str, open_cards: list[CardState], stamp: int) -> list[CardState]:
    """Backlog feature cards are offered a few per turn, the ones covering most records first;
    this meters what is shown, not what is judged (spec 8)."""
    limit = max(int(core.config.understand.backlog_cards_per_turn), 0)
    backlog = [c for c in open_cards if c.kind == "backlog"]
    unseen = sorted((c for c in backlog if c.turn == 0),
                    key=lambda c: (-len(c.questions), c.id))[:limit]
    if not unseen:
        return [c for c in open_cards if _offered(c, stamp)]
    chosen = {c.id for c in unseen}
    own = cardstore.own_cards(core.root, session)
    cardstore.save(core.root, session, [
        dataclasses.replace(c, turn=stamp) if c.id in chosen else c for c in own])
    stamped = [dataclasses.replace(c, turn=stamp) if c.id in chosen else c for c in open_cards]
    return [c for c in stamped if _offered(c, stamp)]


def stop_parts(ctx: Any, core: Any, turn: Any, *, extra: Sequence[CardState] = (),
               fresh: Sequence[CardState] = (), changes: Mapping[str, Any] | None = None,
               passing: Sequence[str] = (), shown: dict[str, str] | None = None) -> StopParts:
    """The three parts of the stop hook's summary (see the module docstring). Never raises
    for a part that cannot be made: that part is left out.

    Slice 3 (sp7-realign-sp8 C1, C7, C8): ``extra`` are the cards the stop hook builds from
    this turn's facts (a regression, a decision that matters, the records the turn proposed,
    one card per feature); they are kept in the session's ``turn_cards.json`` and drawn at
    every turn end until they are moot (``_moot``). ``fresh`` are drawn this turn only
    because the stop hook rebuilds them each turn while they hold (a merge conflict, an early
    conflict). ``changes`` maps a card id to its change with evidence; ``passing`` are the
    test nodes that pass now (a regression card of one is moot). Every card is drawn in full
    (``fullcard``, SR-116); ``shown`` is filled with ``{record id: version shown}`` of every
    record a drawn card showed (the stated set's ``shown``)."""
    session = str(getattr(ctx, "session_id", "") or files.CLI_SESSION)
    turn = turn if isinstance(turn, Mapping) else {}
    started = float(turn.get("turn_start") or 0) or time.time()
    deadline = getattr(ctx, "deadline", None)
    roomy = deadline is None or deadline.remaining_s() > UNDER_BUDGET_S
    told = Told(core.root, session, _iso(started))
    confirmations = _confirmations(core, turn, told)
    refreshed = None
    if roomy:
        try:
            refreshed = settle.refresh(
                core, session,
                recalibrate=deadline is None or deadline.remaining_s() > CALIBRATE_S)
        except Exception:  # noqa: BLE001 - the upkeep never costs the owner their summary
            refreshed = None
    if roomy:
        try:
            from plumb.understand import backlog

            backlog.resume(core, session)    # a pass a failure interrupted goes on (spec 8)
        except Exception:  # noqa: BLE001 - queueing never costs the owner their summary
            pass
    settled: list[str] = []
    titles, digests = settled_line(core, told)
    if titles:
        listed = "; ".join(owner_text.SETTLED_UNDO_LINE.format(title=t) for t in titles)
        settled.append(f"{owner_text.SETTLED_LINE.format(titles=listed)}. "
                       f"{owner_text.SETTLED_HOW}")
    told.settled.update(digests)
    told.dirty = told.dirty or bool(digests)
    for key, text in (refreshed.notices if refreshed is not None else ()):
        if key not in told.notices:
            settled.append(text)
            told.notices.add(key)
            told.dirty = True
    told.save()
    rendered: tuple[str, ...] = ()
    try:
        rendered = tuple(_cards(core, session, refreshed, int(started), deadline,
                                extra=extra, fresh=fresh, changes=changes or {},
                                passing=set(passing), shown=shown))
    except Exception:  # noqa: BLE001 - a card that cannot be made is left out, not fatal
        rendered = ()
    return StopParts(confirmations=confirmations, settled=tuple(settled), cards=rendered)


# --------------------------------------------------------------------------- the cards

TURN_CARDS = "turn_cards.json"   # the cards the stop hook built, kept while they hold
WAITING = "cards_waiting.json"   # what the next prompt tells the agent (SR-116 EX-4)
DRAW_MIN_S = 0.08                # a card's full content needs about this much of the budget


def _held(core: Any, session: str) -> list[tuple[CardState, Any]]:
    raw = files.read_json(files.session_dir(core.root, session) / TURN_CARDS)
    out = []
    for item in raw if isinstance(raw, list) else ():
        if isinstance(item, Mapping) and isinstance(item.get("card"), Mapping):
            out.append((cardstore.card_from_json(item["card"]), item.get("change")))
    return out


def _keep(core: Any, session: str, held: Sequence[tuple[CardState, Any]]) -> None:
    files.write_json_atomic(files.session_dir(core.root, session) / TURN_CARDS, [
        {"card": cardstore.card_to_json(c), "change": change} for c, change in held])


def _moot(core: Any, card: CardState, statuses: Mapping[str, Any],
          passing: set[str]) -> CardState | None:
    """The card as it still holds, or None when its question no longer stands: a proposed
    record confirmed or settled since leaves its feature card (SR-012 EX-1: a settled record
    shows only in the settled line), a decision confirmed since needs no card, a regression
    whose test passes again is over. Nothing the owner has to answer is dropped here."""
    index = core.index()

    def done(record_id: str | None) -> bool:
        if not record_id or record_id not in index:
            return True
        state = statuses.get(record_id)
        return state is not None and (state.confirmation == "confirmed" or bool(state.settled)
                                      or state.superseded_by is not None)

    if card.kind == "proposed":
        left = [q.record for q in card.questions if not done(q.record)]
        if not left:
            return None
        if len(left) == len(card.questions):
            return card
        rebuilt = card_text.proposed_cards(index, [str(i) for i in left], turn=card.turn)
        return rebuilt[0] if rebuilt else None
    if card.kind in ("decision", "early_conflict"):
        return None if all(done(q.record) for q in card.questions) else card
    if card.kind == "regression":
        node = card.evidence.split(" ", 1)[0]
        return None if node in passing or any(
            q.text in passing for q in card.questions) else card
    return card


def _repeats_at_turn_end(card: CardState) -> bool:
    """Whether an open card is drawn at this turn end. Every open card is (DEC-034: until the
    owner presses Leave open, the card shows at the end of every turn).

    TODO(slice 4, DEC-034): after the owner presses Leave open (status ``left_open``, written
    by ``plumb mod press``), the card stops repeating here until its record changes, and stays
    listed under what awaits the owner in the band and the pane. That press is the only thing
    that may make this return False; nothing in slice 3 resolves, expires or hides a card."""
    return card.status == "open"


def _turn_cards(core: Any, session: str, extra: Sequence[CardState], passing: set[str],
                changes: Mapping[str, Any], open_records: set[str]) -> list[tuple[CardState,
                                                                               Any]]:
    """The cards the stop hook built, this turn's and the earlier turns' that still hold;
    written back so they are drawn again at the next turn end."""
    held = {c.id: (c, change) for c, change in _held(core, session)}
    for card in extra:
        held[card.id] = (card, changes.get(card.id) or (held.get(card.id) or (None, None))[1])
    wanted = sorted({q.record for c, _ in held.values() for q in c.questions if q.record})
    statuses = core.status(wanted) if wanted else {}
    out: list[tuple[CardState, Any]] = []
    for card, change in held.values():
        still = _moot(core, card, statuses, passing)
        if still is not None and still.kind == "proposed":
            # a record another open card asks about is asked there, not twice
            keep = [q.record for q in still.questions if q.record not in open_records]
            if not keep:
                continue
            if len(keep) != len(still.questions):
                rebuilt = card_text.proposed_cards(core.index(), [str(i) for i in keep],
                                                   turn=still.turn)
                still = rebuilt[0] if rebuilt else None
        if still is not None:
            out.append((still, change))
    if out or held:
        _keep(core, session, out)
    return out


def _cards(core: Any, session: str, refreshed: Any, stamp: int, deadline: Any, *,
           extra: Sequence[CardState] = (), fresh: Sequence[CardState] = (),
           changes: Mapping[str, Any] | None = None, passing: set[str] | None = None,
           shown: dict[str, str] | None = None) -> list[str]:
    from plumb import stale
    from plumb.understand import fullcard

    new: list[CardState] = []
    if refreshed is not None:
        new.extend(refreshed.cards)
    new.extend(card_text.undone_cards(core, session, turn=stamp))
    if new:
        own = cardstore.own_cards(core.root, session)
        have = {c.id for c in own}
        add = [c for c in new if c.id not in have]
        if add:
            cardstore.save(core.root, session, [*own, *add])
    open_cards = [c for c in cardstore.load(core.root, session) if _repeats_at_turn_end(c)]
    open_cards = _meter(core, session, open_cards, stamp)
    open_cards.extend(_failure_cards(core, session))
    asked = {q.record for c in open_cards for q in c.questions if q.record}
    built = _turn_cards(core, session, extra, passing or set(), changes or {}, asked)
    change_of = {c.id: change for c, change in built}
    seen = {c.id for c in open_cards}
    every = [*open_cards, *(c for c, _ in built if c.id not in seen),
             *(c for c in fresh if c.id not in seen)]
    entries = {f"stale:{e.get('link', '')}": e for e in stale.read_cards(core.root, session)
               if e.get("status", "open") == "open"}
    out: list[str] = []
    drawn: list[str] = []
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
            item = fullcard.content(core, card, session=session,
                                    change=change_of.get(card.id) or (changes or {}).get(
                                        card.id))
        out.append(fullcard.render(item))
        drawn.append(card.topic)
        if shown is not None:
            for question in card.questions:
                if question.record:
                    shown.setdefault(question.record, question.hash)
    if late:
        out.append(owner_text.FULL_NOT_DRAWN.format(
            n=len(late), topics="; ".join(f'"{t}"' for t in late)))
    if incomplete:
        out.append(owner_text.FULL_INCOMPLETE.format(n=incomplete))
    _waiting(core, session, drawn)
    return out


def _waiting(core: Any, session: str, topics: Sequence[str]) -> None:
    """What the next prompt tells the agent (SR-116 EX-4): how many cards the owner was shown
    and their topics, so the reply names them in one line and never restates them."""
    path = files.session_dir(core.root, session) / WAITING
    if not topics:
        try:
            path.unlink()
        except OSError:
            pass
        return
    files.write_json_atomic(path, {"n": len(topics), "topics": list(topics)})


def waiting_line(root: Any, session: str) -> str | None:
    """The agent's one line about the cards waiting for the owner (SR-116 EX-4), or None."""
    raw = files.read_json(files.session_dir(root, session) / WAITING)
    if not isinstance(raw, Mapping) or not raw.get("n"):
        return None
    topics = [str(t) for t in raw.get("topics") or ()]
    named = "; ".join(f'"{t}"' for t in topics[:5]) + (
        f" and {len(topics) - 5} more" if len(topics) > 5 else "")
    return owner_text.CARDS_WAITING_AGENT.format(n=int(raw["n"]), topics=named)
