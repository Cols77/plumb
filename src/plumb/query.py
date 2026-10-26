"""Relevant records and the session brief (spec 6.1, 6.2): context, never procedure."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from plumb.contracts import Record
from plumb.text import overlap, terms

if TYPE_CHECKING:
    from plumb.api import Core

HARD_CAP = 40
_ID_IN_TEXT = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")


def superseded_ids(index: Mapping[str, Record]) -> set[str]:
    return {link.target.record for record in index.values() for link in record.links
            if link.kind == "supersedes" and link.target.record}


def retired_ids(index: Mapping[str, Record]) -> set[str]:
    """Superseded records whose links stop being tracked (SR-164): not those an older record
    supersedes (SR-076 over SR-150), which the owner has yet to settle. A record marked
    ``frozen: true`` (SR-380) counts nowhere either."""
    def num(rid: str) -> tuple[str, int]:
        prefix, _, n = rid.partition("-")
        return prefix, int(n) if n.isdigit() else 0

    return {link.target.record for record in index.values() for link in record.links
            if link.kind == "supersedes" and link.target.record
            and not (num(link.target.record)[0] == num(record.id)[0]
                     and num(link.target.record)[1] > num(record.id)[1])
            } | {record.id for record in index.values() if record.fields.get("frozen")}


def record_text(record: Record) -> str:
    fields = record.fields
    parts: list[str] = [record.title]
    for key in ("statement", "readback", "description", "question", "chosen", "quote"):
        value = fields.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
    for example in record.examples:
        parts.extend((example.given, example.when, example.then, example.criterion))
    return " ".join(parts)


def relevant(core: Core, text: str, limit: int = 5) -> list[tuple[str, float]]:
    """IDs named in ``text`` first, then term overlap; superseded records left out."""
    index = core.index()
    out: list[tuple[str, float]] = []
    for position, match in enumerate(_ID_IN_TEXT.findall(text)):
        if match in index and all(match != i for i, _ in out):
            out.append((match, 100.0 - position * 0.01))
    wanted = terms(text)
    superseded = superseded_ids(index)
    named = {i for i, _ in out}
    scored = []
    for record_id, record in index.items():
        if record_id in named or record_id in superseded:
            continue
        score = overlap(wanted, terms(record_text(record)))
        if score > 0:
            scored.append((record_id, round(score, 4)))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return (out + scored)[:limit]


def _clip(text: str, width: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3] + "..."


def brief_lines(core: Core, max_lines: int = 30, *, show_all: bool = False) -> list[str]:
    """The intent brief: about 30 lines, never more than 40 unless ``show_all``."""
    from plumb.present.cards import awaiting_lines, judge_label

    cap = max_lines if show_all else min(max_lines, HARD_CAP)
    index = core.index()
    statuses = core.status()
    superseded = superseded_ids(index)
    live = {i: r for i, r in index.items() if i not in superseded}

    def of_kind(kind: str) -> list[Record]:
        return [r for _, r in sorted(live.items()) if r.kind == kind]

    header = "plumb brief (records in .plumb/, test map in .plumb/test_map.txt)"
    features = []
    for feature in of_kind("feature"):
        members = {str(s) for s in feature.fields.get("requirements") or []}
        members |= {r.id for r in of_kind("requirement")
                    if str(r.fields.get("feature")) == feature.id}
        features.append(f"{feature.id} {feature.title} ({len(members)} SR)")
    feature_line = "features: " + (", ".join(features) if features else "none")

    intent_items: list[tuple[str, list[str]]] = []
    for label, wanted in (("intent (confirmed):", "confirmed"),
                          ("intent (proposed or edited, awaiting you):", None)):
        items = []
        for record in of_kind("intent"):
            state = statuses[record.id].confirmation
            if (wanted == "confirmed") != (state == "confirmed"):
                continue
            quote = record.fields.get("quote")
            if isinstance(quote, list):
                quote = " / ".join(map(str, quote))
            judged = judge_label(statuses[record.id])        # SR-251
            items.append("  " + _clip(f"{record.id} {record.title}"
                                      + (f" ({judged})" if judged else "")
                                      + (f": \"{quote}\"" if quote else "")))
        if items:
            intent_items.append((label, items))

    # counted, no id and no approve hint (SR-267): the judge's questions, what waits on it
    awaiting = awaiting_lines(core, {i: s for i, s in statuses.items() if i not in superseded})

    decisions = [r for r in of_kind("decision") if r.fields.get("matters") is True
                 and statuses[r.id].confirmation != "confirmed"]
    decision_line = ("decisions that matter, unconfirmed: "
                     + "; ".join(_clip(f"{r.id} {r.title}", 60) for r in decisions[:3])
                     + (f"; +{len(decisions) - 3} more" if len(decisions) > 3 else "")
                     ) if decisions else None

    states = [s for status in statuses.values() for s in status.links]
    stale = [s for s in states if s.state == "stale"]
    dangling = [s for s in states if s.state == "dangling"]
    uncovered = sum(len(s.uncovered_examples) for s in statuses.values())
    drift = f"drift: stale {len(stale)}"
    if stale:
        drift += f" ({stale[0].link.id} {stale[0].moved} moved)"
    drift += f" | dangling {len(dangling)} | uncovered examples {uncovered}"

    open_ncs = [r for r in of_kind("nc") if str(r.fields.get("status", "open")) == "open"]
    nc_line = None
    if open_ncs:
        shown = open_ncs if show_all else open_ncs[:5]
        nc_line = "open NCs: " + "; ".join(_clip(f"{r.id} {r.title}", 50) for r in shown)
        if len(shown) < len(open_ncs):
            nc_line += f"; +{len(open_ncs) - len(shown)} more (plumb brief --all)"

    fixed_before = [header, feature_line]
    fixed_after = [line for line in (*awaiting, decision_line, drift, nc_line) if line]
    budget = cap - len(fixed_before) - len(fixed_after)
    intent_lines: list[str] = []
    total_items = sum(len(items) for _, items in intent_items)
    for label, items in intent_items:
        intent_lines.append(label)
        intent_lines.extend(items)
    if not show_all and len(intent_lines) > max(budget, 0):
        kept: list[str] = []
        kept_items = 0
        for line in intent_lines[: max(budget - 1, 0)]:
            kept.append(line)
            if line.startswith("  "):
                kept_items += 1
        if budget > 0:
            kept.append(f"  +{total_items - kept_items} more (plumb brief --all)")
        intent_lines = kept
    lines = fixed_before + intent_lines + fixed_after
    return lines if show_all else lines[:cap]
