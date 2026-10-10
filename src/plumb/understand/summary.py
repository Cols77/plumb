"""The end-of-turn summary of the understanding layer (JUDGE, SR-105).

``stop_parts`` gives the stop hook, in the order of SR-105:

1. what the owner confirmed by their words ("you said ...", READ's ``confirmation_lines``);
2. one settled line, "Settled from your words: <title> (Undo); <title> (Undo)", with the notices
   that are said once (settling switched itself on for requirements);
3. the cards: clarify, trial batch, backlog feature, goes beyond your words, contradicts,
   couldn't check, then the others (a record to look at, the offer to settle intents, a stale
   link), each as ``cards.render`` writes it.

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
        if entry.kind != "approval" or payload.get("by") != "owner-words"                 or entry.digest in told.confirmed:
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
                                       resolutions=options),) if options else ()))
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


def stop_parts(ctx: Any, core: Any, turn: Any) -> StopParts:
    """The three parts of the stop hook's summary (see the module docstring). Never raises
    for a part that cannot be made: that part is left out."""
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
        rendered = tuple(_cards(core, session, refreshed, int(started), roomy))
    except Exception:  # noqa: BLE001 - a card that cannot be made is left out, not fatal
        rendered = ()
    return StopParts(confirmations=confirmations, settled=tuple(settled), cards=rendered)


def _cards(core: Any, session: str, refreshed: Any, stamp: int, roomy: bool) -> list[str]:
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
    open_cards = cardstore.load(core.root, session)
    open_cards = _meter(core, session, open_cards, stamp)
    open_cards.extend(_failure_cards(core, session))
    shown: Sequence[CardState] = sorted(open_cards, key=card_text.kind_rank)
    return [card_text.render(c) for c in shown]
