"""The escalated spec: a set of records the owner approves by one set-hash approval (sp2 6.2,
SR-037).

The set is anchored on an ``INT`` with ``mode: escalated`` and a ``members`` list. One
``approval`` event confirms the anchor and every member at their hashes and carries
``set: {anchor, hash}``, where the hash is ``sha256(canonical_json(sorted [id, hash]
pairs))`` over the anchor and its members. An edit of any member afterwards makes that member
an unconfirmed edit and the set ``unconfirmed``. No command writes it: the judge worker does (SR-210, SR-380).
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


SET_LINKS = ("derives_from", "decides")


def _anchors(core: Core) -> dict[str, Any]:
    return {r.id: r for r in core.index().values()
            if r.kind == "intent" and r.fields.get("mode") == "escalated"}


def escalated_sets(core: Core) -> tuple[dict[str, list[str]], dict[str, str]]:
    """``({anchor: [record ids]}, {record id: anchor})``: THE membership rule of an escalated
    set (R8 B "never for an escalated spec set"). A record belongs to the set when the anchor
    lists it in ``members`` or when it derives from or decides the anchor or another record
    of the set (``plumb capture`` with ``"intent": "INT-x"``, ``plumb new``/``decide``
    against it): such a record joins the set hash, so the set needs the owner again."""
    index = core.index()
    anchors = _anchors(core)
    sets: dict[str, list[str]] = {}
    owner: dict[str, str] = {}
    for anchor_id, anchor in sorted(anchors.items()):
        declared = [str(m) for m in anchor.fields.get("members") or [] if isinstance(m, str)]
        sets[anchor_id] = []
        for member in declared:
            if member not in anchors and member not in owner:
                owner[member] = anchor_id
                sets[anchor_id].append(member)
    grew = True
    while grew:
        grew = False
        for record_id, record in sorted(index.items()):
            if record_id in anchors or record_id in owner:
                continue
            for link in record.links:
                target = link.target.record
                if link.kind not in SET_LINKS or not target:
                    continue
                anchor_id = target if target in anchors else owner.get(target)
                if anchor_id is not None:
                    owner[record_id] = anchor_id
                    sets[anchor_id].append(record_id)
                    grew = True
                    break
    return sets, owner


def set_ids(core: Core, anchor: str) -> list[str]:
    """The anchor, its declared members, then the records that derive from the set."""
    declared = members(core, anchor)
    missing = [i for i in [anchor, *declared] if i not in core.index()]
    if missing:
        raise SpecError(f"{anchor} names members that do not exist: {', '.join(missing)}")
    sets, _ = escalated_sets(core)
    return [anchor, *declared, *[i for i in sets.get(anchor, []) if i not in declared]]


def current_set_hash(core: Core, anchor: str) -> str:
    index = core.index()
    return set_hash([(i, index[i].hash) for i in set_ids(core, anchor)])


def set_of(core: Core) -> dict[str, str]:
    """``{record id: anchor}`` for every record of an escalated set (declared members and
    records deriving from the set; ``escalated_sets``). The anchors are not keys."""
    return escalated_sets(core)[1]


def escalated_ids(core: Core) -> frozenset[str]:
    """Every anchor and every record of an escalated set: none is ever auto-approved."""
    return frozenset(_anchors(core)) | frozenset(set_of(core))


def in_escalated_set(core: Core, record_id: str) -> bool:
    return record_id in escalated_ids(core)


def _set_approvals(core: Core, anchor: str) -> list[LogEntry]:
    from plumb.confirm import checked

    return [entry for entry, problem in checked(core)
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
    """``plumb spec show``: every member in full, the set hash and how it is approved (P6: a
    set is approved whole; no approve command is named, SR-267)."""
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
    lines.append("the judge approves the set whole on your behalf, or asks you about it")
    return lines


def waiting_line(core: Core, anchor: str) -> str | None:
    """The stop hook's line while the set waits for the owner (sp2 6.2)."""
    if set_state(core, anchor) == "approved":
        return None
    return (f"plumb: {anchor} (escalated) waits for the owner's approval of its set; do not "
            "write its code yet")
