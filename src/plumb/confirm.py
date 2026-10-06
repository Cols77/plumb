"""Derived confirmation states (spec 5.6). Nothing here is stored: every state is computed
from the records' current hashes and the ``approval`` and ``revocation`` events.

- proposed: no (unrevoked, valid) approval of the record exists;
- confirmed: the latest such approval pins the record's current hash;
- unconfirmed-edit: an approval exists but pins an older hash, or (requirements) an approval
  pinned the content of a ``verified_by`` end that has changed since (``changed_tests``): an
  owner-confirmed example's acceptance test cannot change meaning, or be rewritten to pass,
  without the owner seeing it;
- covered (requirements): confirmed, and every example has a verified_by link to an
  existing test.

An approval that fails its re-check (an owner approval written under the agent session marker,
an agent-relayed approval without its cited prompt, affirming quote or quote digest, or a
``by: import`` approval that the import event it carries, written outside the agent session,
did not approve: ``importer/recheck.py``) never confirms anything; ``plumb validate`` reports
it as an error.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import LogEntry, Record, RecordStatus
from plumb.log import entry_digest
from plumb.normalize import sha256_text

if TYPE_CHECKING:
    from plumb.api import Core


def affirmation_in(quote: str, affirmations: Sequence[str]) -> str | None:
    """The first configured affirmation term found in ``quote`` as a whole word or phrase."""
    lowered = quote.lower()
    for term in affirmations:
        words = [re.escape(w) for w in term.lower().split()]
        if not words:
            continue
        pattern = r"(?<![\w])" + r"\s+".join(words) + r"(?![\w])"
        if re.search(pattern, lowered):
            return term
    return None


def entry_problem(entry: LogEntry, prompt_digests: set[str],
                  affirmations: Sequence[str]) -> str | None:
    """Why an approval or revocation entry fails its re-check, or None (spec 5.6)."""
    payload: Mapping[str, Any] = entry.payload
    if entry.digest != entry_digest({"v": 1, "kind": entry.kind, "at": entry.at,
                                     "marker": entry.marker, "payload": dict(payload),
                                     "prev": entry.prev}):
        return f"{entry.kind} entry does not match its digest (modified)"
    by = payload.get("by")
    if by == "import":  # upstream human consent pinning the imported content (next-plan 9.3)
        from plumb.importer.recheck import import_problem

        return import_problem(entry)  # self-contained: needs no log context
    if by == "owner":
        if entry.marker != "none":
            return (f"owner {entry.kind} written under the agent session marker "
                    f"({entry.marker})")
        return None
    if by == "agent-relayed":
        digest = payload.get("prompt_digest")
        if not digest or digest not in prompt_digests:
            return f"agent-relayed {entry.kind} cites no earlier prompt event"
        quote = payload.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            return f"agent-relayed {entry.kind} carries no owner quote"
        if payload.get("quote_digest") != sha256_text(quote):
            return f"agent-relayed {entry.kind} quote does not match its quote_digest"
        if entry.kind == "approval" and affirmation_in(quote, affirmations) is None:
            return "agent-relayed approval quote contains no affirmation"
        return None
    if by == "import":
        return "import approvals are not accepted in this build (spec F11)"
    return f"{entry.kind} has an unknown source by={by!r}"


def checked_entries(entries: Iterable[LogEntry],
                    affirmations: Sequence[str]) -> list[tuple[LogEntry, str | None]]:
    """Approval and revocation entries in log order, each with its re-check problem."""
    prompts: set[str] = set()
    out: list[tuple[LogEntry, str | None]] = []
    for entry in entries:
        if entry.kind == "prompt":
            digest = entry.payload.get("digest")
            if isinstance(digest, str):
                prompts.add(digest)
        elif entry.kind in ("approval", "revocation"):
            out.append((entry, entry_problem(entry, prompts, affirmations)))
    return out


def remaining_approvals(entries: Iterable[LogEntry],
                        affirmations: Sequence[str]) -> dict[str, list[tuple[str, str]]]:
    """Per record, the valid approvals ``(hash, by)`` left after revocations, in order."""
    remaining: dict[str, list[tuple[str, str]]] = {}
    for entry, problem in checked_entries(entries, affirmations):
        if problem is not None:
            continue
        by = str(entry.payload.get("by"))
        for item in entry.payload.get("records") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            record_id, record_hash = item["id"], str(item.get("hash"))
            approvals = remaining.setdefault(record_id, [])
            if entry.kind == "approval":
                approvals.append((record_hash, by))
            elif approvals:
                kept = [a for a in approvals if a[0] != record_hash]
                remaining[record_id] = kept if len(kept) < len(approvals) else approvals[:-1]
    return remaining


def verified_end(link: Any) -> str | None:
    """The key an approval pins a ``verified_by`` end under: its test node or path."""
    if link.kind != "verified_by":
        return None
    target = link.target
    return target.test or target.path


def approved_test_pins(entries: Iterable[LogEntry], affirmations: Sequence[str],
                       index: Mapping[str, Record]) -> dict[str, dict[str, set[str]]]:
    """``{SR: {verified_by end: content hashes}}``: what the owner's approvals of each
    requirement at its current hash pinned for its acceptance tests (approvals still standing
    after revocations). An approval written before ends were pinned pins nothing."""
    standing: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for entry, problem in checked_entries(entries, affirmations):
        if problem is not None:
            continue
        for item in entry.payload.get("records") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            record_id, record_hash = item["id"], str(item.get("hash"))
            kept = standing.setdefault(record_id, [])
            if entry.kind == "approval":
                pins = item.get("verified")
                kept.append((record_hash, pins if isinstance(pins, Mapping) else {}))
            elif kept:
                rest = [k for k in kept if k[0] != record_hash]
                standing[record_id] = rest if len(rest) < len(kept) else kept[:-1]
    out: dict[str, dict[str, set[str]]] = {}
    for record_id, kept in standing.items():
        record = index.get(record_id)
        if record is None:
            continue
        for record_hash, pins in kept:
            if record_hash != record.hash:
                continue
            for end, digest in pins.items():
                out.setdefault(record_id, {}).setdefault(str(end), set()).add(str(digest))
    return out


def changed_tests(states: Iterable[Any], pinned: Mapping[str, set[str]]) -> tuple[str, ...]:
    """The ``verified_by`` ends whose current content no approval pinned (a missing end
    counts: deleting a confirmed example's test is a change too)."""
    out: list[str] = []
    for state in states:
        end = verified_end(state.link)
        if end is None or end not in pinned:
            continue
        now = state.current.target if state.current is not None else None
        if now is None or now not in pinned[end]:
            if end not in out:
                out.append(end)
    return tuple(out)


def confirmation_of(record: Record,
                    approvals: Sequence[tuple[str, str]]) -> tuple[str, str | None]:
    if not approvals:
        return "proposed", None
    latest_hash, by = approvals[-1]
    if latest_hash == record.hash:
        return "confirmed", by
    return "unconfirmed-edit", by


def statuses(core: Core, ids: Iterable[str] | None = None) -> dict[str, RecordStatus]:
    index = core.index()
    selected = list(index) if ids is None else [i for i in ids if i in index]
    approvals = remaining_approvals(core.events(), core.config.approve.affirmations)
    pins = approved_test_pins(core.events(), core.config.approve.affirmations, index)
    states = core.link_states(selected)
    by_record: dict[str, list] = {}
    for state in states:
        by_record.setdefault(state.link.source, []).append(state)
    superseded: dict[str, str] = {}
    for record in index.values():
        for link in record.links:
            if link.kind == "supersedes" and link.target.record in index:
                superseded[link.target.record] = record.id
    out: dict[str, RecordStatus] = {}
    for record_id in selected:
        record = index[record_id]
        confirmation, by = confirmation_of(record, approvals.get(record_id, []))
        record_states = tuple(by_record.get(record_id, ()))
        uncovered: tuple[str, ...] = ()
        covered = False
        moved: tuple[str, ...] = ()
        if record.kind == "requirement" and confirmation == "confirmed" and record_id in pins:
            moved = changed_tests(record_states, pins[record_id])
            if moved:
                confirmation = "unconfirmed-edit"
        if record.kind == "requirement":
            verified = [s for s in record_states
                        if s.link.kind == "verified_by" and s.state != "dangling"]
            named = {s.link.example for s in verified if s.link.example}
            uncovered = tuple(e.id for e in record.examples if e.id not in named)
            has_cover = bool(verified) if not record.examples else not uncovered
            covered = confirmation == "confirmed" and has_cover
        out[record_id] = RecordStatus(
            id=record_id, confirmation=confirmation,  # type: ignore[arg-type]
            approved_by=by,  # type: ignore[arg-type]
            covered=covered, uncovered_examples=uncovered, links=record_states,
            superseded_by=superseded.get(record_id), changed_tests=moved)
    return out
