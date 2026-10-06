"""The escalated spec: a set of records the owner approves by one set-hash approval (sp2 6.2,
SR-037).

The set is anchored on an ``INT`` with ``mode: escalated`` and a ``members`` list. One
``approval`` event confirms the anchor and every member at their hashes and carries
``set: {anchor, hash}``, where the hash is ``sha256(canonical_json(sorted [id, hash]
pairs))`` over the anchor and its members. An edit of any member afterwards makes that member
an unconfirmed edit and the set ``unconfirmed``. Owner form: ``plumb spec approve`` through
``approvals.require_owner``; relayed form: ``plumb relay --set`` with the owner's own words.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.normalize import canonical_json, sha256_bytes

if TYPE_CHECKING:
    from plumb.api import Core
    from plumb.contracts import LogEntry

SetState = str  # "approved" | "unconfirmed" | "unapproved"


class SpecError(ValueError):
    """Not an escalated set (exit 1)."""


def set_hash(pairs: Sequence[tuple[str, str]]) -> str:
    return sha256_bytes(canonical_json(sorted([str(i), str(h)] for i, h in pairs)))


def members(core: Core, anchor: str) -> list[str]:
    """The anchor's ``members``; ``SpecError`` when ``anchor`` is not an escalated INT."""
    record = core.index().get(anchor)
    if record is None or record.kind != "intent":
        raise SpecError(f"no intent {anchor}")
    if record.fields.get("mode") != "escalated":
        raise SpecError(f"{anchor} is not an escalated spec (mode: escalated)")
    raw = record.fields.get("members") or []
    return [str(m) for m in raw if isinstance(m, str)]


def set_ids(core: Core, anchor: str) -> list[str]:
    ids = [anchor, *members(core, anchor)]
    missing = [i for i in ids if i not in core.index()]
    if missing:
        raise SpecError(f"{anchor} names members that do not exist: {', '.join(missing)}")
    return ids


def current_set_hash(core: Core, anchor: str) -> str:
    index = core.index()
    return set_hash([(i, index[i].hash) for i in set_ids(core, anchor)])


def set_of(core: Core) -> dict[str, str]:
    """``{member id: anchor}`` for every escalated set (members never auto-approve)."""
    out: dict[str, str] = {}
    for record in core.index().values():
        if record.kind == "intent" and record.fields.get("mode") == "escalated":
            for member in record.fields.get("members") or []:
                out[str(member)] = record.id
    return out


def _set_approvals(core: Core, anchor: str) -> list[LogEntry]:
    from plumb.confirm import checked_entries

    return [entry for entry, problem in checked_entries(core.events(),
                                                        core.config.approve.affirmations)
            if problem is None and entry.kind == "approval"
            and isinstance(entry.payload.get("set"), Mapping)
            and entry.payload["set"].get("anchor") == anchor]


def set_state(core: Core, anchor: str) -> SetState:
    """``approved`` when a set approval pins the current set hash and every record of the
    set is confirmed; ``unconfirmed`` when a set approval exists but no longer holds;
    ``unapproved`` otherwise."""
    try:
        ids = set_ids(core, anchor)
    except SpecError:
        return "unapproved"
    approvals = _set_approvals(core, anchor)
    if not approvals:
        return "unapproved"
    current = current_set_hash(core, anchor)
    statuses = core.status(ids)
    if approvals[-1].payload["set"].get("hash") == current and all(
            statuses[i].confirmation == "confirmed" for i in ids):
        return "approved"
    return "unconfirmed"


def set_payload(core: Core, anchor: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The approval's records (with their pins) and ``{anchor, hash}``."""
    from plumb.approvals import approval_items

    ids = set_ids(core, anchor)
    records = approval_items(core, ids)
    return records, {"anchor": anchor,
                     "hash": set_hash([(r["id"], r["hash"]) for r in records])}


def show_lines(core: Core, anchor: str) -> list[str]:
    """``plumb spec show``: every member in full, the set hash and the approval command."""
    from plumb.readback import record_lines

    index = core.index()
    ids = set_ids(core, anchor)
    statuses = core.status(ids)
    lines = [f"escalated spec {anchor}: {index[anchor].title} ({set_state(core, anchor)})"]
    for record_id in ids:
        record = index[record_id]
        lines.append(f"{record_id} ({record.kind}, {statuses[record_id].confirmation})")
        lines.extend("  " + line for line in record_lines(record))
    lines.append(f"set hash: {current_set_hash(core, anchor)}")
    lines.append(f"approve (owner's terminal): plumb spec approve {anchor}; in a session the "
                 f"agent relays your words: plumb relay --set {anchor} --prompt <digest> "
                 "--quote \"<your words>\"")
    return lines


def approve_set(core: Core, anchor: str, *, note: str = "") -> LogEntry:
    """``plumb spec approve``: the owner's one set-hash approval, from the owner's own
    terminal only (``approvals.require_owner``)."""
    from plumb.approvals import refuse_under_marker, require_owner

    refuse_under_marker("spec approve")
    records, digest = set_payload(core, anchor)
    require_owner("spec approve", f"approve the escalated spec {anchor} and its "
                  f"{len(records) - 1} members at their current content (set "
                  f"{digest['hash'][:19]}), as yourself (by: owner)?")
    payload = {"records": records, "set": digest, "by": "owner", "prompt_digest": None,
               "quote": None, "quote_digest": None, "affirmation": None, "stated_set": None,
               "note": note}
    return core.log_append("events", "approval", payload)


def waiting_line(core: Core, anchor: str) -> str | None:
    """The stop hook's line while the set waits for the owner (sp2 6.2)."""
    if set_state(core, anchor) == "approved":
        return None
    return (f"plumb: {anchor} (escalated) waits for the owner's approval of its set; do not "
            "write its code yet")
