"""Derived confirmation states (spec 5.6). Nothing here is stored: every state is computed
from the records' current hashes and the ``approval`` and ``revocation`` events.

- proposed: no (unrevoked, valid) approval of the record exists;
- confirmed: the latest such approval pins the record's current hash;
- unconfirmed-edit: an approval exists but pins an older hash;
- covered (requirements): confirmed, and every example has a verified_by link to an
  existing test.

An approval that fails its re-check (an owner approval written under the agent session marker,
or an agent-relayed approval without its cited prompt, affirming quote or quote digest) never
confirms anything; ``plumb validate`` reports it as an error.
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
            superseded_by=superseded.get(record_id))
    return out
