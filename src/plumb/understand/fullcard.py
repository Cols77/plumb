"""Every owner card drawn at the end of a turn, and for the mod (SR-129, INT-036, DEC-039).

A card is one of two shapes and has one renderer. A ``readback`` (a request's, or a trial of one
record) is a proposal, the assumptions the owner could flip and the one thing not done. A
``choice`` is one question, its two lines of context and options that each say what they do,
the recommended one first. ``content(core, card)`` gives plain data:

``{id, kind, topic, issue, context: [<=2 lines], assumptions: [...], wont: str | None,
options: [{n, text, consequence, recommended}], diagram, turn, status}``

The options and what each does are the ones stored on the card's question, so a button that was
reworded still applies its stored answer. Nothing plumb writes shows a record id, a digest or
one of plumb's own words (``cards.plain``); the owner's quoted words are left as written, and an
option with no consequence is printed alone, never with a placeholder. Nothing here resolves,
hides or expires a card."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from plumb.contracts import CardState
from plumb.present import owner_text
from plumb.understand import cardcontent
from plumb.understand.cards import plain

READBACK = ("clarify", "trial")
CONTEXT_MAX = 2
# no better-supported answer (SR-131)
NO_RECOMMENDATION = ("trial", "choice", "beyond", "contradicts", "early_conflict", "clarify")
_QUOTED = re.compile(r'("[^"]*")')


def _say(text: Any, index: Mapping[str, Any]) -> str:
    """``text`` through ``plain``, the owner's quoted words left as written."""
    out = []
    for n, part in enumerate(_QUOTED.split(str(text))):
        if n % 2 or not part.strip():
            out.append(part)
        else:
            out.append(part[:len(part) - len(part.lstrip())] + plain(part, index)
                       + part[len(part.rstrip()):])
    return "".join(out).strip()


def _options(choices: list[tuple[str, str]], index: Mapping[str, Any],
             recommended: bool = True) -> list[dict[str, Any]]:
    return [{"n": n, "text": _say(text, index), "consequence": _say(said, index) or None,
             "recommended": recommended and n == 1}
            for n, (text, said) in enumerate(choices, start=1)]


def content(core: Any, card: CardState) -> dict[str, Any]:
    """The content of a card plumb built (any kind but a stale link or a drift, which
    ``stale_content`` draws from the card the agent filed)."""
    from plumb.understand import clarify

    index = core.index()
    question = card.questions[0] if card.questions else None
    choices = [(c.label, c.consequence) for c in (question.choices if question else ())] \
        or [(label, "") for label in card.resolutions]
    readback = card.kind in READBACK
    assumed, wont, context, doubts = [], "", [], []
    marks = (clarify.EVIDENCE_ASSUMED.format(text=""), clarify.EVIDENCE_WONT.format(text=""))
    for line in (raw.strip() for raw in card.evidence.splitlines()):
        if not line or line == clarify.ESCALATION_MARK:
            continue
        if readback and line.startswith(marks[0]):
            assumed.append(line[len(marks[0]):])
        elif readback and line.startswith(marks[1]):
            wont = wont or line[len(marks[1]):]
        elif readback and "Yes confirms" in line:      # SR-152 doubt lines: never cut
            doubts.append(line)
        else:
            context.append(line)
    if card.kind == "trial" and question:
        context.append(question.text)         # the one thing asked, after the owner's words
    return {
        "id": card.id, "kind": card.kind,
        "topic": _say(card.topic, index), "issue": _say(card.issue, index),
        "context": [_say(line, index) for line in (*context[:CONTEXT_MAX], *doubts)],
        "assumptions": [_say(a, index) for a in assumed],
        "wont": _say(wont, index) or None,
        # a merge conflict recommends only a combined version that was actually proposed
        "options": _options(choices, index, card.kind not in NO_RECOMMENDATION and (
            card.kind != "conflict" or bool(question and question.choices
                                            and question.choices[0].answer == "accepted"))),
        "diagram": card.diagram, "turn": card.turn,
        "status": card.status}


def _drift(core: Any, entry: Mapping[str, Any]) -> str:
    """SR-113 EX-2: the request behind the change a diagnosis filed (the card's own line)."""
    from plumb.understand.repin import turn_before

    path = str(entry.get("path") or "")
    turn = None
    if path and not path.startswith(("INT-", "SR-", "DEC-", "FEAT-", "NC-")):
        try:
            turn = turn_before(core, path)
        except Exception:  # noqa: BLE001 - the request is evidence, never required
            turn = None
    return (owner_text.DRIFT_REQUEST.format(text=turn["text"], at=turn["at"]) if turn
            else owner_text.DRIFT_NO_REQUEST)


def stale_content(core: Any, entry: Mapping[str, Any], *, session: str = "") -> dict[str, Any]:
    """A stale card the agent or the diagnosis filed, as the same content: its options and what
    each does, and why the first is recommended as the context line; a drift (filed by the
    diagnosis) adds the request behind the change."""
    from plumb import stale

    index = core.index()
    link = str(entry.get("link") or "")
    why = str(entry.get("why") or "").strip()
    drift = str(entry.get("by") or "") == "diagnosis"
    context = [*([why] if why else []), *([_drift(core, entry)] if drift else [])]
    return {
        "id": f"stale:{link}", "kind": "drift" if drift else "stale_link",
        "session": session, "link": link, "record": str(entry.get("record") or ""),
        "topic": _say(entry.get("topic") or "", index),
        "issue": _say(entry.get("issue") or "", index),
        "context": [_say(line, index) for line in context[:CONTEXT_MAX]],
        "assumptions": [], "wont": None,
        "options": _options([(o["text"], o["consequence"] or "")
                             for o in cardcontent.options(entry)], index),
        "diagram": "", "turn": int(entry.get("turn") or 0),
        "status": str(entry.get("status") or "open"), "missing": stale.card_missing(entry)}


def lines(item: Mapping[str, Any]) -> list[str]:
    """The card as the owner reads it: the topic, the proposal or question, the context, then
    (a read-back) its assumptions and the one thing not done, then the options."""
    from plumb.understand.clarify import EVIDENCE_ASSUMED, EVIDENCE_WONT

    out = [owner_text.FULL_DIAGRAM.format(path=item["diagram"])] if item["diagram"] else []
    out.append(item["topic"])
    if item["issue"] and item["issue"] != item["topic"]:       # a record titled by its proposal
        out.append(item["issue"])
    out += item["context"]
    out += [EVIDENCE_ASSUMED.format(text=a) for a in item["assumptions"]]
    if item["wont"]:
        out.append(EVIDENCE_WONT.format(text=item["wont"]))
    for option in item["options"]:
        out.append(owner_text.FULL_OPTION.format(
            n=option["n"], text=option["text"],
            mark=owner_text.FULL_RECOMMENDED if option["recommended"] else "")
            + (owner_text.FULL_CONSEQUENCE.format(text=option["consequence"])
               if option["consequence"] else ""))
    return out


def render(item: Mapping[str, Any]) -> str:
    return "\n".join(lines(item))
