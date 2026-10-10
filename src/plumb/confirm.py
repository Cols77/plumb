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
from collections.abc import Collection, Iterable, Mapping, Sequence
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
    if by in ("owner-words", "settled", "undone"):  # SP8: re-checked by the understand layer
        from plumb.understand.recheck import problem

        reason = problem(entry, None)
        if reason is None and by == "owner-words"                 and payload.get("prompt_digest") not in prompt_digests:
            return f"owner-words {entry.kind} cites no earlier prompt event"
        return reason
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
        choice = payload.get("choice")
        if entry.kind == "approval" and isinstance(choice, Mapping):
            # the owner's pick between the options a conflict card showed ("keep feat-x's",
            # "keep this one", "both"): the quote names the chosen option (R17)
            from plumb.awareness.answer import choice_named

            if not choice_named(quote, choice):
                return "agent-relayed approval quote does not name the option chosen"
            return None
        if entry.kind == "approval" and affirmation_in(quote, affirmations) is None:
            return "agent-relayed approval quote contains no affirmation"
        return None
    if by == "auto-jev":
        if entry.kind != "approval":
            return f"auto-jev {entry.kind}: only the owner revokes"
        return None  # re-checked in log order by checked_entries (sp2 8.2)
    return f"{entry.kind} has an unknown source by={by!r}"


def checked_entries(entries: Iterable[LogEntry], affirmations: Sequence[str],
                    escalated: Collection[str] = ()) -> list[tuple[LogEntry, str | None]]:
    """Approval and revocation entries in log order, each with its re-check problem.
    ``escalated``: the records of escalated spec sets (``escalated_of``), which no auto-jev
    approval confirms; callers holding a Core use ``checked``/``remaining``."""
    from plumb.capture.autoapprove import recheck

    prompts: set[str] = set()
    calibrations: dict[str, LogEntry] = {}
    config: Mapping[str, Any] | None = None
    approved: set[str] = set()  # records with an owner, relayed or imported approval
    out: list[tuple[LogEntry, str | None]] = []
    for entry in entries:
        if entry.kind == "prompt":
            digest = entry.payload.get("digest")
            if isinstance(digest, str):
                prompts.add(digest)
        elif entry.kind == "config":
            settings = entry.payload.get("auto_approve")
            owner = entry.marker == "none" and entry.payload.get("by") == "owner"
            if owner and isinstance(settings, Mapping):
                config = settings
        elif entry.kind == "calibration":
            calibrations[entry.digest] = entry
        elif entry.kind in ("approval", "revocation"):
            problem = entry_problem(entry, prompts, affirmations)
            by = entry.payload.get("by")
            if problem is None and by == "auto-jev":
                problem = recheck(entry, config, calibrations, prompts, approved, escalated)
            if problem is None and entry.kind == "approval" and by != "auto-jev":
                approved.update(str(r.get("id")) for r in entry.payload.get("records") or []
                                if isinstance(r, Mapping))
            out.append((entry, problem))
    return out


# R13 Q4: the label of every confirmation resting on a prompt the agent recorded itself
SELF_RECORDED = "self-recorded message"


def is_self_recorded(payload: Mapping[str, Any]) -> bool:
    """Whether an approval rests on a message the agent recorded itself (R13 Q4): an
    agent-relayed approval whose cited prompt was not logged by the host's prompt hook
    (``plumb relay`` writes ``self_recorded``). The one test every surface (``plumb show``,
    ``plumb explain``, the merge glance, ``plumb hosts status``) labels by."""
    return payload.get("by") == "agent-relayed" and payload.get("self_recorded") is True


def remaining_entries(entries: Iterable[LogEntry], affirmations: Sequence[str],
                      escalated: Collection[str] = ()
                      ) -> dict[str, list[tuple[str, str, LogEntry]]]:
    """Per record, the valid approvals ``(hash, by, entry)`` left after revocations, in
    order (the entry carries the labels: ``self_recorded``, the auto-jev score, a set)."""
    remaining: dict[str, list[tuple[str, str, LogEntry]]] = {}
    for entry, problem in checked_entries(entries, affirmations, escalated):
        if problem is not None:
            continue
        by = str(entry.payload.get("by"))
        for item in entry.payload.get("records") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            record_id, record_hash = item["id"], str(item.get("hash"))
            approvals = remaining.setdefault(record_id, [])
            if entry.kind == "approval":
                approvals.append((record_hash, by, entry))
            elif approvals:
                kept = [a for a in approvals if a[0] != record_hash]
                remaining[record_id] = kept if len(kept) < len(approvals) else approvals[:-1]
    return remaining


def escalated_of(core: Core) -> frozenset[str]:
    """The records of escalated spec sets (``plumb.capture.spec.escalated_ids``), which
    no auto-jev approval confirms."""
    from plumb.capture.spec import escalated_ids

    return escalated_ids(core)


def checked(core: Core) -> list[tuple[LogEntry, str | None]]:
    """``checked_entries`` of ``core``'s event log with every re-check input (the one entry
    point for callers holding a Core)."""
    return checked_entries(core.events(), core.config.approve.affirmations, escalated_of(core))


def remaining(core: Core) -> dict[str, list[tuple[str, str, LogEntry]]]:
    standing = remaining_entries(core.events(), core.config.approve.affirmations,
                                 escalated_of(core))
    return carry_renumbers(core, standing)[0]


def carry_renumbers(core: Core, standing: dict[str, list[tuple[str, str, LogEntry]]]
                    ) -> tuple[dict[str, list[tuple[str, str, LogEntry]]], dict[str, str]]:
    """The approvals a ``renumber`` carries to the new ID while the words are unchanged
    (sp6 5.4, R17), and ``{new id: old id}`` for the records confirmed only that way. The
    one choke point every confirmation reader goes through (``statuses``, ``remaining``);
    nothing is imported when the log holds no ``renumber`` entry."""
    if not any(e.kind == "renumber" for e in core.events()):
        return standing, {}
    from plumb.ids.aliases import carry, revocations_of

    return carry(core, standing, revocations_of(checked(core)))


def pinned_through_renumbers(core: Core, pairs: Iterable[tuple[LogEntry, str | None]]
                             ) -> list[tuple[LogEntry, str | None, list[Mapping[str, Any]]]]:
    """``pairs`` (``checked_entries`` output), each entry with the records it pins read
    through every ``renumber`` (sp6 5.4, R17): an approval a renumber carries pins the new ID
    at its current hash too, the old item's other fields (``ends``, ``verified``) kept. The
    one choke point for the readers of what an approval pinned outside the confirmation
    states (``merge.approved_ends``, ``boundary.report._set_confirmed``); nothing is
    imported when the log holds no ``renumber`` entry."""
    carried: Mapping[tuple[str, str, str], tuple[str, str]] = {}
    if any(e.kind == "renumber" for e in core.events()):
        from plumb.ids.aliases import carried_items

        carried = carried_items(core)
    out: list[tuple[LogEntry, str | None, list[Mapping[str, Any]]]] = []
    for entry, problem in pairs:
        items = [r for r in entry.payload.get("records") or [] if isinstance(r, Mapping)]
        if carried and entry.kind == "approval":
            for item in list(items):
                hit = carried.get((entry.digest, str(item.get("id")), str(item.get("hash"))))
                if hit is not None:
                    items.append({**item, "id": hit[0], "hash": hit[1]})
        out.append((entry, problem, items))
    return out


def remaining_approvals(entries: Iterable[LogEntry], affirmations: Sequence[str],
                        escalated: Collection[str] = ()) -> dict[str, list[tuple[str, str]]]:
    """Per record, the valid approvals ``(hash, by)`` left after revocations, in order."""
    return {record_id: [(h, by) for h, by, _ in approvals]
            for record_id, approvals in remaining_entries(entries, affirmations,
                                                          escalated).items()}


def self_recorded_approvals(entries: Iterable[LogEntry], affirmations: Sequence[str],
                            escalated: Collection[str] = ()) -> int:
    """How many valid approvals rest on a self-recorded message (R13 Q4)."""
    return sum(1 for entry, problem in checked_entries(entries, affirmations, escalated)
               if problem is None and entry.kind == "approval"
               and is_self_recorded(entry.payload))


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
    standing, carried = carry_renumbers(
        core, remaining_entries(core.events(), core.config.approve.affirmations,
                                escalated_of(core)))
    approvals = {r: [(h, by) for h, by, _ in items] for r, items in standing.items()}
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
        latest = standing.get(record_id)
        self_recorded = bool(confirmation != "proposed" and latest
                             and is_self_recorded(latest[-1][2].payload))
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
            superseded_by=superseded.get(record_id), changed_tests=moved,
            self_recorded=self_recorded,
            settled=confirmation == "confirmed" and by == "settled",
            carried_from=carried.get(record_id) if confirmation == "confirmed" else None)
    return out
