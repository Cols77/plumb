"""The open cards of a session: ``cards.json`` (this module is its one writer, frozen in phase
C) plus, read-only, STALE's ``stale_cards.json`` as ``stale_link`` cards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import CARD_STATUSES, CardState, ClarifyAnswer, ClarifyQuestion
from plumb.understand import files


def card_to_json(card: CardState) -> dict[str, Any]:
    return {"id": card.id, "kind": card.kind, "topic": card.topic, "issue": card.issue,
            "evidence": card.evidence, "resolutions": list(card.resolutions),
            "questions": [files.question_to_json(q) for q in card.questions],
            "status": card.status, "answers": [files.answer_to_json(a) for a in card.answers],
            "turn": card.turn, "branch": card.branch, "diagram": card.diagram}


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
        turn=int(data.get("turn") or 0), branch=str(data.get("branch") or ""),
        diagram=str(data.get("diagram") or ""))


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


# the statuses of a card that still asks the owner at the end of a turn and that the reader
# reads the owner's next message against: ``change_requested`` waits for the owner's words
# (SR-086 EX-7, EX-8); ``left_open`` does not repeat until its record changes (DEC-034)
AWAITING: tuple[str, ...] = ("open", "change_requested")


def _head_is(git: Path, branch: str) -> bool:
    try:
        return (git / "HEAD").read_text(encoding="utf-8").strip() == "ref: refs/heads/" + branch
    except OSError:
        return False


def branch_gone(root: Path, branch: str) -> bool:
    """Whether ``branch`` has neither a ref file nor a packed-refs line (files only, no git
    process). A worktree's ``.git`` file leads to its git dir, whose ``commondir`` holds refs.
    The branch HEAD points at is never gone (an unborn branch has no ref yet), and a
    repository using reftable keeps no ref files to look in."""
    git = root / ".git"
    try:
        if git.is_file():
            git = (root / git.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
            if _head_is(git, branch):
                return False
            common = git / "commondir"
            if common.is_file():
                git = (git / common.read_text(encoding="utf-8").strip()).resolve()
        if not git.is_dir() or _head_is(git, branch) or (git / "reftable").is_dir():
            return False
        if (git / "refs" / "heads" / branch).is_file():
            return False
        packed = git / "packed-refs"
        return not (packed.is_file() and any(
            line.rstrip().endswith(" refs/heads/" + branch)
            for line in packed.read_text(encoding="utf-8").splitlines()))
    except (OSError, IndexError):
        return False


def load(root: Path, session: str, *, open_only: bool = True) -> list[CardState]:
    """The session's cards: its own, then the stale-link ones (``open_only``: the awaiting
    ones, ``AWAITING``). A card of a branch that is gone is left out (SR-132 EX-3)."""
    cards = [c for c in (*own_cards(root, session), *stale_cards(root, session))
             if not (c.branch and branch_gone(root, c.branch))]
    return [c for c in cards if c.status in AWAITING] if open_only else cards


def withdraw(root: Path, session: str, ids: Sequence[str]) -> None:
    """Withdraw the session's cards ``ids`` (SR-132 EX-4): they confirm nothing and their
    records stay proposed."""
    from dataclasses import replace

    cards = own_cards(root, session)
    save(root, session, [replace(c, status="withdrawn") if c.id in ids else c for c in cards])


def withdraw_card(core: Any, session: str, card: CardState, why: str) -> None:
    """Withdraw one card (own or stale-link) and log why; it is told at the next turn end."""
    if card.kind == "stale_link":
        from plumb import stale

        stale.withdraw_card(core, session, card.id.removeprefix("stale:"), why)
        return
    withdraw(core.root, session, [card.id])
    core.log_append("events", "card-withdrawn", {"card": card.id, "session": session,
                                                 "topic": card.topic, "reason": why})


def save(root: Path, session: str, cards: Sequence[CardState]) -> None:
    """Write the session's own cards (stale-link cards are STALE's and never written)."""
    files.write_json_atomic(files.cards_path(root, session),
                            [card_to_json(c) for c in cards if c.kind != "stale_link"])


def answer_presses(core: Any, session: str) -> list[dict[str, Any]]:
    """The session's logged presses that answer a card: not Leave open or Ask for a change,
    but a merge conflict card's side buttons are ``change`` presses that do answer."""
    from plumb.contracts import CARD_PRESS
    from plumb.understand import cards

    sides = (cards.KEEP_THIS, cards.KEEP_OTHER, cards.BOTH)
    return [e.payload for e in core.log_read("events", [CARD_PRESS])
            if e.payload.get("session") == session
            and (e.payload.get("answer") != "open"
                 and (e.payload.get("answer") != "change" or e.payload.get("label") in sides))]


def states(core: Any, session: str) -> dict[str, tuple[str, str]]:
    """SR-160: where each of the session's cards stands, as ``id -> (state, reason)``:
    ``waiting`` (awaiting the owner), ``processing`` (every question answered by a logged
    press, not applied yet), ``blocked`` (a press that found the record changed since it was
    shown: the reason, decided at press time), ``done`` (answered or closed), ``left_open``;
    withdrawn cards are left out. Cards the stop hook built are read from what it drew."""
    from plumb.present import owner_text
    from plumb.understand import summary

    presses = answer_presses(core, session)
    index = core.index()
    out: dict[str, tuple[str, str]] = {}
    for card in load(core.root, session, open_only=False):
        mine = [p for p in presses if p.get("card") == card.id]
        if card.status == "open":
            asked = {q.id for q in card.questions}
            out[card.id] = ("processing" if mine and asked <= {p.get("question") for p in mine}
                            else "waiting", "")
        elif card.status == "change_requested":
            out[card.id] = ("waiting", "")
        elif card.status == "left_open":
            out[card.id] = ("left_open", "")
        elif card.status in ("answered", "closed"):
            gone = next((p for p in mine if p.get("stale")), None)
            title = index[gone["record"]].title if gone and gone["record"] in index else (
                gone["record"] if gone else "")
            out[card.id] = (("blocked", owner_text.PRESS_CHANGED_SINCE.format(title=title))
                            if gone else ("done", ""))
    left = summary.turn_left(core.root, session)
    for entry in summary.read_drawn(core.root, session):
        cid = str(entry["card"].get("id"))
        if entry.get("turn_built") and cid not in out:
            out[cid] = (("done" if any(p.get("card") == cid for p in presses) else
                         "left_open" if cid in left else "waiting"), "")
    return out
