"""Every owner card drawn in full at the end of a turn (SR-116, INT-031; sp7-realign-sp8 C7).

``content(core, card)`` gives, for a card of any kind, what the owner needs to choose without
asking back, as plain data shaped like ``cardcontent.card_content`` (the stale-link card's):

``{id, kind, session, topic, issue, evidence, items: [{text, record_now}],
record_now: {id, kind, title, wording, examples, details} | None,
change: {path, diff, size, lines, added, removed, folded, note} | None,
owner_words: {items: [{id, title, quote, prompt, at, found, found_lines}], note},
options: [{n, text, consequence, recommended, index}], why, missing, complete, notes}``.

The record as it now reads and the owner's words are derived each time from the records; what
each option does and leaves undone, and why the first is recommended, come from the owner-text
tables for the kinds plumb builds, and from the card itself for the cards the agent or the
model files (a stale link, a drift). ``render(content)`` writes it as the end-of-turn text: the
head, the items, the evidence, the record, the change (a diff over ``FOLD_AT`` folded with its
size, never cut), the owner's words, the options with their consequences, the reason.

Nothing here resolves, hides or expires a card."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import CardState
from plumb.present import owner_text
from plumb.understand import cardcontent

# the kinds whose cards the agent or the model writes: a card of these missing a part is not
# offered (SR-116 EX-3); the kinds plumb builds carry every part by construction
AGENT_FILED = frozenset({"stale_link", "drift"})


def _filled(table: Mapping[str, str], label: str) -> str | None:
    """``label``'s entry in ``table``; a template key ("Keep {side}'s version") matches any
    filling, and its text is filled with the same values."""
    if label in table:
        return table[label]
    for template, text in table.items():
        if "{" not in template:
            continue
        pattern = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>.+)", re.escape(template))
        found = re.fullmatch(pattern, label)
        if found:
            try:
                return text.format(**found.groupdict())
            except (KeyError, IndexError):
                return text
    return None


def consequence(kind: str, label: str) -> str | None:
    """What choosing ``label`` on a ``kind`` card does and leaves undone (None when unknown)."""
    said = _filled(owner_text.CONSEQUENCES, label)
    if said is None:
        said = owner_text.CONSEQUENCE_PICK.get(kind)
    return said


def wording(record: Any) -> dict[str, Any]:
    """``cardcontent.record_wording`` plus ``details``: an intent's will, won't and labelled
    assumptions, a decision's alternatives (SR-012 EX-3: never only an ID or a title)."""
    out = cardcontent.record_wording(record)
    # one line per part: a decision's question and choice read "question: ...; chosen: ..."
    out["wording"] = "; ".join(" ".join(part.split()) for part in str(out["wording"]).splitlines()
                               if part.strip())
    fields = record.fields
    details: list[str] = []

    def items(raw: Any) -> list[str]:
        raw = [raw] if isinstance(raw, str) else raw or []
        return [" ".join(str(i).split()) for i in raw if str(i).strip()]

    if record.kind == "intent":
        details += [f"will: {w}" for w in items(fields.get("will"))]
        details += [f"won't: {w}" for w in items(fields.get("wont"))]
        for assumption in fields.get("assumptions") or []:
            if isinstance(assumption, Mapping):
                label = str(assumption.get("id") or "").strip()
                text = " ".join(str(assumption.get("text") or "").split())
                details.append(f"assumed ({label}): {text}" if label else f"assumed: {text}")
            elif str(assumption).strip():
                details.append(f"assumed: {' '.join(str(assumption).split())}")
    elif record.kind == "decision":
        details += [f"also fits: {a}" for a in items(fields.get("alternatives"))]
    out["details"] = details
    return out


def owner_words(core: Any, records: Sequence[Any]) -> dict[str, Any]:
    """The owner's words ``records`` trace to (``cardcontent.owner_words`` over several records,
    the prompt log read once, each intent named once). ``found`` is what a transcript search
    found for the intent (``cardcontent.recovered``, SR-118) and ``found_lines`` says it in
    plain words (the span, its date and session, "found in a transcript, not verified", and
    for a misreading the proposed rewording): shown, never trusted."""
    index = core.index()
    sources: dict[str, Any] = {}
    for record in records:
        if record.kind == "intent":
            sources.setdefault(record.id, record)
        for link in record.links:
            if link.kind == "derives_from" and link.target.record in index:
                sources.setdefault(link.target.record, index[link.target.record])
    prompts = cardcontent._prompts(core) if sources else []
    out = []
    for source in sources.values():
        raw = source.fields.get("quote") or ""
        parts = raw if isinstance(raw, (list, tuple)) else [raw]
        quote = " / ".join(" ".join(str(p).split()) for p in parts if str(p).strip())
        prompt = cardcontent._prompt_for(prompts, str(source.fields.get("prompt") or ""))
        found = cardcontent.recovered(core, source)
        if not quote and prompt is None and found is None:
            continue
        out.append({"id": source.id, "title": source.title, "quote": quote or None,
                    "prompt": prompt["text"] if prompt else None,
                    "at": prompt["at"] if prompt else None, "found": found,
                    "found_lines": cardcontent.found_lines(found)})
    note = ""
    if not out:
        names = "; ".join(r.title for r in records) or "this"
        note = cardcontent.NO_WORDS.format(title=names)
    return {"items": out, "note": note}


def _options(kind: str, resolutions: Sequence[str]) -> list[dict[str, Any]]:
    return [{"n": n, "text": str(text), "consequence": consequence(kind, str(text)),
             "recommended": n == 1, "index": n - 1}
            for n, text in enumerate(resolutions, start=1)]


def _drift(core: Any, out: dict[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    """SR-113 EX-2: a stale card the diagnosis filed is a drift card: it names the intent the
    requirement still agrees with and the request behind the change."""
    from plumb.understand.repin import turn_before

    out["kind"] = "drift"
    said = [owner_text.DRIFT_INTENT.format(title=item["title"])
            for item in out["owner_words"]["items"]]
    path = str(entry.get("path") or "")
    turn = None
    if path and not path.startswith(("INT-", "SR-", "DEC-", "FEAT-", "NC-")):
        try:
            turn = turn_before(core, path)
        except Exception:  # noqa: BLE001 - the request is evidence, never required
            turn = None
    said.append(owner_text.DRIFT_REQUEST.format(text=turn["text"], at=turn["at"])
                if turn else owner_text.DRIFT_NO_REQUEST)
    out["evidence"] = "; ".join(said)
    out["request"] = turn
    return out


def stale_content(core: Any, entry: Mapping[str, Any], *, session: str = "") -> dict[str, Any]:
    """A stale card's full content (``cardcontent.card_content``), as a drift card when the
    diagnosis filed it."""
    from plumb.understand.cards import plain

    out = cardcontent.card_content(core, entry, session=session)
    out.setdefault("evidence", "")
    out.setdefault("items", [])
    index = core.index()      # the notes name records by title, never by a bare number
    if out["change"].get("note"):
        out["change"]["note"] = plain(out["change"]["note"], index)
    if out["owner_words"].get("note"):
        out["owner_words"]["note"] = plain(out["owner_words"]["note"], index)
    if str(entry.get("by") or "") == "diagnosis":
        return _drift(core, out, entry)
    return out


def content(core: Any, card: CardState, *, session: str = "",
            change: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The full content of a card plumb built (any kind but a stale link or a drift, which
    ``stale_content`` draws from the card the agent filed). ``change`` is the change with its
    evidence when the card's facts carry one (a regression's diff)."""
    index = core.index()
    questions = list(card.questions)
    records = [index[q.record] for q in questions if q.record and q.record in index]
    single = len(questions) <= 1
    items = [] if single else [
        {"text": q.text, "record_now": wording(index[q.record])
         if q.record and q.record in index else None} for q in questions]
    options = _options(card.kind, card.resolutions)
    why = owner_text.WHY_RECOMMENDED.get(card.kind) if options else None
    notes = []
    if any(o["consequence"] is None for o in options):
        notes.append(f"what each option does and leaves undone is {cardcontent.NOT_WRITTEN}")
    return {
        "id": card.id, "kind": card.kind, "session": session, "topic": card.topic,
        "issue": card.issue, "evidence": card.evidence, "items": items,
        "record_now": wording(records[0]) if single and records else None,
        "change": dict(change) if change else None,
        "owner_words": owner_words(core, records) if records else {"items": [], "note": ""},
        "options": options, "why": why, "missing": [], "complete": True, "notes": notes,
        "turn": card.turn, "status": card.status,
    }


def _record_lines(now: Mapping[str, Any], *, item: bool = False) -> list[str]:
    lines = []
    if not item:
        lines.append(owner_text.FULL_READS.format(title=now["title"], wording=now["wording"]))
    elif now["wording"] and now["wording"] != now["title"]:
        lines.append(owner_text.FULL_DETAIL.format(text=now["wording"]))
    for text in [*(now.get("examples") or ()), *(now.get("details") or ())]:
        lines.append(owner_text.FULL_DETAIL.format(text=text))
    return lines


def _change_lines(change: Mapping[str, Any] | None, fold: bool) -> list[str]:
    if not change:
        return []
    lines = []
    if change.get("diff"):
        lines.append(owner_text.FULL_CHANGE.format(
            path=change.get("path") or "", added=change.get("added", 0),
            removed=change.get("removed", 0), size=change.get("size", 0)))
        if change.get("folded") and fold:
            lines.append(owner_text.FULL_FOLDED.format(size=change.get("size", 0),
                                                       lines=change.get("lines", 0)))
        else:
            lines += [owner_text.FULL_DETAIL.format(text=line)
                      for line in str(change["diff"]).splitlines()]
    if change.get("note"):
        lines.append(owner_text.FULL_CHANGE_NOTE.format(note=change["note"]))
    return lines


def lines(item: Mapping[str, Any], *, fold: bool = True) -> list[str]:
    """The card as the owner reads it at the end of a turn, every part in turn."""
    from plumb.understand.cards import HEADS

    head = HEADS.get(str(item["kind"]), owner_text.CARD_GENERIC)
    out = [head.format(topic=item["topic"], issue=item["issue"])]
    for entry in item.get("items") or ():
        out.append(owner_text.CARD_ITEM.format(text=entry["text"]))
        if entry.get("record_now"):
            out += _record_lines(entry["record_now"], item=True)
    if item.get("evidence") and item["kind"] != "clarify":  # SR-147
        out.append(owner_text.CARD_EVIDENCE.format(evidence=item["evidence"]))
    if item.get("record_now"):
        out += _record_lines(item["record_now"])
    out += _change_lines(item.get("change"), fold)
    words = item.get("owner_words") or {}
    for said in words.get("items") or ():
        text = said.get("quote") or said.get("prompt") or ""
        out.append(owner_text.FULL_WORDS.format(title=said["title"], said=text) if text
                   else owner_text.FULL_WORDS_UNLOGGED.format(title=said["title"]))
        if said.get("prompt") and said.get("quote") and said["prompt"] != said["quote"]:
            out.append(owner_text.FULL_WORDS_PROMPT.format(text=said["prompt"]))
        found = said.get("found_lines")
        if found is None:
            found = cardcontent.found_lines(said.get("found"))
        out += [owner_text.FULL_DETAIL.format(text=line) for line in found]
    if words.get("note"):
        out.append(owner_text.FULL_WORDS_NONE.format(note=words["note"]))
    for option in item.get("options") or ():
        mark = owner_text.FULL_RECOMMENDED if option["recommended"] else ""
        out.append(owner_text.FULL_OPTION.format(n=option["n"], text=option["text"], mark=mark))
        out.append(owner_text.FULL_CONSEQUENCE.format(
            text=option["consequence"] or owner_text.FULL_NOT_WRITTEN))
    if item.get("options"):
        out.append(owner_text.FULL_WHY.format(text=item.get("why")
                                              or owner_text.FULL_NOT_WRITTEN))
    return out


def render(item: Mapping[str, Any], *, fold: bool = True) -> str:
    return "\n".join(lines(item, fold=fold))
