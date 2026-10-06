"""``plumb explain <anything>``: why a behaviour, a file or a record exists, in the owner's
terms (ruling R9, "the user don't necessarily know the code").

The argument is plain language ("the doubling thing"), a record ID or a repository path; IDs
and paths work but are never required. It resolves, in this order:

1. record IDs named in the text (``SR-001``, ``INT-003`` ...);
2. a repository path (a file, or the end of a link): the requirements that own it;
3. plain words: the records whose title, statement, examples or quote share the most terms
   (``plumb.query.relevant``), best first.

For each record it prints the upward chain: the requirement, the owner's words it derives
from (INT quote), the decisions that decide it, its feature, its examples, the state of the
tests that verify them, and the code it is implemented by. ``plumb why`` is an alias. The host
agent runs it for ``/plumb explain`` and restates the answer for the owner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MAX_MATCHES = 3

_STATE = {"confirmed": "confirmed", "proposed": "proposed, awaiting your confirmation",
          "unconfirmed-edit": "changed since you confirmed it, awaiting you"}


def _clip(text: Any, width: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _state(status: Any) -> str:
    if status is None:
        return "?"
    state = _STATE.get(status.confirmation, status.confirmation)
    if status.confirmation == "confirmed":
        by = getattr(status, "approved_by", None)
        state += {"owner": " by you", "agent-relayed": " by you (relayed from chat)"}.get(
            str(by), f" ({by})" if by else "")
    return state


def resolve(core: Any, query: str) -> tuple[list[str], str, str | None]:
    """``(record ids, how, path)``: what ``query`` names. ``how`` is ``id``, ``path``,
    ``words`` or ``none``; ``path`` is the repository path when the query is one."""
    from plumb.hashing import clean_rel_path
    from plumb.query import _ID_IN_TEXT, relevant

    index = core.index()
    text = " ".join(query.split())
    named = [i for i in dict.fromkeys(_ID_IN_TEXT.findall(text)) if i in index]
    if named:
        return named, "id", None
    rel = clean_rel_path(text.strip("'\"")) if text and " " not in text else None
    if rel is not None:
        owners = list(core.records_for_paths([rel]).get(rel, ()))
        if owners or (Path(core.root) / rel).exists():
            requirements = [i for i in owners if index[i].kind == "requirement"]
            return sorted(requirements or owners), "path", rel
    scored = [(i, score) for i, score in relevant(core, text, limit=MAX_MATCHES * 3)
              if score > 0]
    if not scored:
        return [], "none", None
    best = scored[0][1]
    picked = [i for i, score in scored if score >= best * 0.5][:MAX_MATCHES]
    return picked, "words", None


def _tests(core: Any, record_id: str) -> list[str]:
    """``tests/test_mod.py (EX-1): passing``: each acceptance test with its state."""
    try:
        from plumb.verify import open_verify
    except ImportError:
        return []
    try:
        items = open_verify(core).acceptance([record_id]).get(record_id, [])
    except Exception:  # noqa: BLE001 - a lane failure degrades to no test line
        return []
    out = []
    for item in items:
        if item.get("masked"):
            state = "passes only because the test was changed; awaiting you"
        elif item.get("failing"):
            state = "regression: it passed before and fails now" if item.get("regression") \
                else "failing"
        elif item.get("unverified"):
            state = "never run" if item.get("state") == "none" else \
                "not rerun since the code changed"
        else:
            state = "passing"
        examples = f" ({', '.join(item['examples'])})" if item.get("examples") else ""
        out.append(f"{item['test']}{examples}: {state}")
    return out


def _example_text(example: Any) -> str:
    if example.criterion:
        return f"{example.id}: {example.criterion}"
    return f"{example.id}: given {example.given}, when {example.when}, then {example.then}"


def record_chain(core: Any, record_id: str, statuses: Mapping[str, Any]) -> list[str]:
    """The upward chain of one record, in the owner's terms."""
    index = core.index()
    record = index[record_id]
    fields = record.fields
    lines = [f"{record_id} \"{record.title}\" ({_state(statuses.get(record_id))})"]
    what = (fields.get("statement") or fields.get("readback") or fields.get("description")
            or fields.get("question"))
    if what:
        lines.append("  what: " + _clip(what))
    if record.kind == "intent" and fields.get("quote"):
        quote = fields["quote"]
        quote = " / ".join(map(str, quote)) if isinstance(quote, list) else quote
        lines.append("  your words: \"" + _clip(quote) + "\"")
    if record.kind == "decision":
        if fields.get("chosen"):
            lines.append("  chosen: " + _clip(fields["chosen"]))
        alternatives = fields.get("alternatives") or []
        if alternatives:
            alternatives = [alternatives] if isinstance(alternatives, str) else alternatives
            lines.append("  also possible: " + _clip("; ".join(map(str, alternatives))))
    for link in record.links:
        target = link.target.record
        if link.kind == "derives_from" and target in index:
            parent = index[target]
            quote = parent.fields.get("quote")
            quote = " / ".join(map(str, quote)) if isinstance(quote, list) else quote
            lines.append(f"  why: {target} \"{parent.title}\" ({_state(statuses.get(target))})"
                         + (f", your words: \"{_clip(quote, 120)}\"" if quote else ""))
    for other in index.values():
        if other.kind != "decision":
            continue
        if any(link.kind == "decides" and link.target.record == record_id
               for link in other.links):
            chosen = other.fields.get("chosen")
            lines.append(f"  decided: {other.id} \"{other.title}\""
                         + (f", chosen: {_clip(chosen, 80)}" if chosen else "")
                         + f" ({_state(statuses.get(other.id))})")
    feature = fields.get("feature")
    if feature and feature in index:
        lines.append(f"  feature: {feature} \"{index[feature].title}\"")
    for example in record.examples:
        lines.append("  example " + _clip(_example_text(example)))
    if record.kind == "requirement":
        for test in _tests(core, record_id):
            lines.append("  test " + test)
        code = [link.target.path or link.target.test or link.target.symbol
                for link in record.links if link.kind == "implemented_by"]
        if code:
            lines.append("  code: " + ", ".join(str(c) for c in code))
    if record.kind in ("intent", "feature", "decision"):
        below = sorted(other.id for other in index.values()
                       if any(link.target.record == record_id
                              and link.kind in ("derives_from", "upstream")
                              for link in other.links)
                       or (record.kind == "feature"
                           and str(other.fields.get("feature")) == record_id))
        decided = [link.target.record for link in record.links
                   if link.kind == "decides" and link.target.record]
        below = sorted({*below, *decided})
        if below:
            lines.append("  led to: " + ", ".join(
                f"{i} \"{_clip(index[i].title, 60)}\"" for i in below if i in index))
    return lines


def explain_lines(core: Any, query: str) -> tuple[list[str], dict[str, Any]]:
    """The answer lines and ``{query, how, path, records}``."""
    ids, how, path = resolve(core, query)
    statuses = core.status()
    data: dict[str, Any] = {"query": query, "how": how, "path": path, "records": ids}
    if not ids:
        if how == "path" or path:
            return [f"{path}: no requirement owns this file yet (an untraced change at the "
                    "merge boundary); ask the agent to read it back and record a proposed "
                    "requirement"], data
        return [f"nothing in plumb's records matches \"{query}\"; try other words, a file "
                "path or a record ID (plumb brief lists the records)"], data
    lines: list[str] = []
    if how == "path":
        lines.append(f"{path} is code for:")
    elif how == "words":
        lines.append(f"\"{query}\" best matches:")
    for record_id in ids:
        lines.extend(record_chain(core, record_id, statuses))
    lines.append("plumb show <ID> prints a record in full; plumb impact <ID|path> lists what "
                 "a change would reach.")
    return lines, data


def matches(core: Any, query: str) -> Sequence[str]:
    """The record ids ``query`` resolves to (for tests and the host)."""
    return resolve(core, query)[0]
