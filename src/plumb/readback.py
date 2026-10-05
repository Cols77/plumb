"""The read-back of a record in the owner's terms (spec 6.4, R1).

One rendering serves the end-of-turn summary and ``plumb show``, so what the summary lists
as ``proposed`` and what the owner reads in full are the same lines:

- an intent: its read-back (or quote), then what will and won't be done and every labelled
  assumption;
- a requirement: its statement, then every example as given/when/then (or its criterion);
- a decision: its title and chosen option, then the alternatives;
- any other record: its title.

Lines are whole: nothing is clipped here. A caller that cannot show a line in full must treat
the record as not shown (a bare affirmation then cannot confirm it).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _flat(value: Any) -> str:
    if isinstance(value, list):
        value = " / ".join(map(str, value))
    return " ".join(str(value or "").split())


def _items(raw: Any) -> list[tuple[str | None, str]]:
    """``(id, text)`` of a will/wont/assumptions list whose items are strings or mappings."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    out: list[tuple[str | None, str]] = []
    for item in raw:
        if isinstance(item, dict):
            item_id = item.get("id")
            text = item.get("text") or item.get("statement") or ""
            out.append((None if item_id is None else str(item_id), _flat(text)))
        else:
            out.append((None, _flat(item)))
    return [(i, t) for i, t in out if t]


def _example_text(example: Any) -> str:
    if example.given or example.when or example.then:
        return f"given {example.given}, when {example.when}, then {example.then}"
    return example.criterion


def record_lines(record: Any) -> list[str]:
    """Every line of ``record``'s read-back, each naming the record (no prefix, no clip)."""
    fields = record.fields
    rid = record.id
    lines: list[str] = []
    if record.kind == "intent":
        text = fields.get("readback") or fields.get("quote") or record.title
        lines.append(f"{rid}: {_flat(text)}")
        will = _items(fields.get("will"))
        if will:
            lines.append(f"{rid} will: " + "; ".join(t for _, t in will))
        wont = _items(fields.get("wont"))
        if wont:
            lines.append(f"{rid} won't: " + "; ".join(t for _, t in wont))
        for n, (item_id, text) in enumerate(_items(fields.get("assumptions")), start=1):
            lines.append(f"{rid}/{item_id or f'A-{n}'} assumption: {text}")
    elif record.kind == "requirement":
        lines.append(f"{rid}: {_flat(fields.get('statement') or record.title)}")
        for example in record.examples:
            lines.append(f"{rid}/{example.id}: {_flat(_example_text(example))}")
    elif record.kind == "decision":
        chosen = _flat(fields.get("chosen"))
        lines.append(f"{rid}: {_flat(record.title)}" + (f": {chosen}" if chosen else ""))
        alternatives = _items(fields.get("alternatives"))
        if alternatives:
            lines.append(f"{rid} alternatives: " + "; ".join(t for _, t in alternatives))
    else:
        lines.append(f"{rid}: {_flat(record.title)}")
    return lines


def show_lines(core: Any, ids: Iterable[str]) -> tuple[list[str], list[str]]:
    """``plumb show``: the header, read-back and body of each record; and the unknown ids."""
    index = core.index()
    wanted = [i for i in ids]
    known = [i for i in wanted if i in index]
    statuses = core.status(known) if known else {}
    lines: list[str] = []
    missing: list[str] = []
    for record_id in wanted:
        record = index.get(record_id)
        if record is None:
            missing.append(record_id)
            continue
        if lines:
            lines.append("")
        state = statuses[record_id].confirmation if record_id in statuses else "?"
        lines.append(f"{record_id} ({record.kind}, {state}) {record.path}")
        lines.extend("  " + line for line in record_lines(record))
        body = record.body.strip()
        if body:
            lines.extend("  | " + line for line in body.splitlines())
    return lines, missing
