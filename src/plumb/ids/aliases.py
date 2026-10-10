"""What a ``renumber`` event maps (sp6 5.4, 5.5; R17; SR-071).

- ``approval_aliases``: an approval of the incoming record under its old ID counts for the
  new ID only while the record's current content, with the renumber undone, hashes to the
  approval's pinned hash: the owner's words are byte-identical to what the owner saw. Any
  later edit, or an approval of other content, carries nothing (R17).
- ``carry``: the confirmation reader's choke point (``confirm.statuses`` and
  ``confirm.remaining``): it adds the carried approvals to the new ID and says which
  records are confirmed only by a carried approval, so every surface labels them
  "carried by renumber SR-070 -> SR-081" (``present.owner_text.CARRIED``).
- ``carried_items``: the same carry for the readers of what an approval pinned (its owning
  ``ends``, a set approval's members): ``confirm.pinned_through_renumbers``.
- ``trailer_aliases``: in the incoming commits a ``renumber`` lists, ``SR-070`` means
  ``SR-081``; history is never rewritten.
- ``renumber_problems``: ``plumb validate``'s re-check of every ``renumber`` entry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import LogEntry, Record


def entries(core: Any) -> list[LogEntry]:
    return [e for e in core.events() if e.kind == "renumber"]


def _mapping(payload: Mapping[str, Any]) -> dict[str, str]:
    raw = payload.get("map")
    out = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, Mapping) else {}
    if isinstance(payload.get("from"), str) and isinstance(payload.get("to"), str):
        out[payload["from"]] = payload["to"]
    return out


def reverted_hash(record: Record, mapping: Mapping[str, str]) -> str:
    """The hash ``record`` had before the renumber ``mapping`` (old -> new) rewrote it."""
    from plumb.ids.rewrite import swap_record
    from plumb.model import record_hash

    reverse = {new: old for old, new in mapping.items()}
    data = {"id": record.id, "title": record.title, **dict(record.fields)}
    old_data, old_body, _ = swap_record(data, record.body, reverse)
    return record_hash(old_data, old_body)


def approval_aliases(core: Any) -> dict[tuple[str, str], tuple[str, str]]:
    """``{(new id, current hash): (old id, pinned hash)}`` for each renumbered record whose
    content, with the renumber undone, is still exactly what the incoming approvals
    pinned."""
    found = entries(core)
    if not found:
        return {}
    index = core.index()
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for entry in found:
        payload = entry.payload
        old, new, pinned = payload.get("from"), payload.get("to"), payload.get("old_hash")
        record = index.get(new) if isinstance(new, str) else None
        if record is None or not isinstance(old, str) or not isinstance(pinned, str):
            continue
        if reverted_hash(record, _mapping(payload)) != pinned:
            continue
        out[(new, record.hash)] = (old, pinned)
    return out


def _listed(core: Any) -> dict[str, set[str]]:
    """``{new id: approval digests}`` the renumber entries list."""
    out: dict[str, set[str]] = {}
    for entry in entries(core):
        new = entry.payload.get("to")
        if isinstance(new, str):
            out.setdefault(new, set()).update(
                str(d) for d in entry.payload.get("approvals") or [])
    return out


def carry(core: Any, standing: Mapping[str, list[tuple[str, str, LogEntry]]],
          revocations: Sequence[tuple[str, str]] = ()
          ) -> tuple[dict[str, list[tuple[str, str, LogEntry]]], dict[str, str]]:
    """``standing`` (``{id: [(hash, by, entry)]}`` after revocations) read through every
    ``renumber``: the incoming approvals a renumber lists leave the old ID (they never
    approved the first parent's record, which kept that ID) and count for the new ID while
    its words are unchanged (``approval_aliases``). Returns the result and ``{new id: old
    id}`` for the records whose standing confirmation is a carried one (the R17 label).
    ``revocations``: the ``(id, hash)`` of every valid revocation; revoking the new ID
    drops the carry. An approval pinning the old ID's current words is never moved."""
    found = entries(core)
    out = {k: list(v) for k, v in standing.items()}
    if not found:
        return out, {}
    index = core.index()
    aliases = approval_aliases(core)
    revoked = set(revocations)
    labels: dict[str, str] = {}
    for entry in found:
        payload = entry.payload
        old, new, pinned = payload.get("from"), payload.get("to"), payload.get("old_hash")
        if not (isinstance(old, str) and isinstance(new, str) and isinstance(pinned, str)):
            continue
        kept = index.get(old)
        if old == new or (kept is not None and kept.hash == pinned):
            continue
        listed = {str(d) for d in payload.get("approvals") or []}
        moved = [item for item in out.get(old, [])
                 if item[0] == pinned and item[2].digest in listed]
        if not moved:
            continue
        out[old] = [item for item in out[old] if item not in moved]
        if not out[old]:
            del out[old]
        record = index.get(new)
        if record is None or aliases.get((new, record.hash)) != (old, pinned) or \
                (new, record.hash) in revoked:
            continue
        direct = out.get(new, [])
        out[new] = [(record.hash, by, item) for _, by, item in moved] + direct
        if not direct:
            labels[new] = old
    return out, labels


def carried_items(core: Any) -> dict[tuple[str, str, str], tuple[str, str]]:
    """``{(approval digest, old id, pinned hash): (new id, current hash)}``: each record an
    approval pinned that a ``renumber`` carries to the new ID while its words are unchanged
    (``approval_aliases``, the same conditions as ``carry``). What
    ``confirm.pinned_through_renumbers`` reads every approval's records through."""
    found = entries(core)
    if not found:
        return {}
    index = core.index()
    aliases = approval_aliases(core)
    out: dict[tuple[str, str, str], tuple[str, str]] = {}
    for entry in found:
        payload = entry.payload
        old, new, pinned = payload.get("from"), payload.get("to"), payload.get("old_hash")
        if not (isinstance(old, str) and isinstance(new, str) and isinstance(pinned, str)):
            continue
        kept, record = index.get(old), index.get(new)
        if old == new or (kept is not None and kept.hash == pinned) or record is None or \
                aliases.get((new, record.hash)) != (old, pinned):
            continue
        for digest in payload.get("approvals") or []:
            out[(str(digest), old, pinned)] = (new, record.hash)
    return out


def revocations_of(checked_entries: Sequence[tuple[LogEntry, str | None]]
                   ) -> list[tuple[str, str]]:
    out = []
    for entry, problem in checked_entries:
        if problem is None and entry.kind == "revocation":
            out += [(str(r.get("id")), str(r.get("hash")))
                    for r in entry.payload.get("records") or [] if isinstance(r, Mapping)]
    return out


def trailer_aliases(core: Any) -> dict[tuple[str, str], str]:
    """``{(commit sha, old id): new id}`` for the incoming commits of every renumber."""
    out: dict[tuple[str, str], str] = {}
    for entry in entries(core):
        old, new = entry.payload.get("from"), entry.payload.get("to")
        if not (isinstance(old, str) and isinstance(new, str)):
            continue
        for sha in entry.payload.get("commits") or []:
            out[(str(sha), old)] = new
    return out


def map_trailer(aliases: Mapping[tuple[str, str], str], sha: str,
                ids: Sequence[str]) -> tuple[str, ...]:
    """The trailer IDs of commit ``sha`` read through the renumber map (a full or an
    abbreviated sha)."""
    if not aliases:
        return tuple(ids)
    out = []
    for record_id in ids:
        new = aliases.get((sha, record_id))
        if new is None:
            new = next((v for (s, o), v in aliases.items()
                        if o == record_id and (s.startswith(sha) or sha.startswith(s))),
                       None)
        out.append(new or record_id)
    return tuple(out)


def carried(core: Any) -> dict[str, tuple[str, str]]:
    """``{new id: (old id, new id)}`` of the records confirmed by a carried approval."""
    from plumb.confirm import carry_renumbers, escalated_of, remaining_entries

    standing = remaining_entries(core.events(), core.config.approve.affirmations,
                                 escalated_of(core), core)
    _, labels = carry_renumbers(core, standing)
    return {new: (old, new) for new, old in labels.items()}


def renumber_problems(core: Any) -> list[str]:
    """``plumb validate``: every ``renumber`` entry's listed approvals exist, are valid,
    name the old ID and pin the incoming content (``old_hash``); a record still at the
    entry's ``new_hash`` must hash to ``old_hash`` with the renumber undone."""
    found = entries(core)
    if not found:
        return []
    from plumb.confirm import checked
    from plumb.ids.reservation import split

    approvals = {e.digest: (e, p) for e, p in checked(core) if e.kind == "approval"}
    index = core.index()
    problems = []
    for entry in found:
        payload = entry.payload
        old, new = payload.get("from"), payload.get("to")
        label = f"renumber {old} -> {new} (entry {entry.digest[:19]})"
        old_parts = split(old) if isinstance(old, str) else None
        new_parts = split(new) if isinstance(new, str) else None
        if old_parts is None or new_parts is None or old_parts[0] != new_parts[0]:
            problems.append(f"{label}: from and to are not IDs of one kind")
            continue
        pinned = payload.get("old_hash")
        for digest in payload.get("approvals") or []:
            found_entry = approvals.get(str(digest))
            if found_entry is None:
                problems.append(f"{label}: approval {str(digest)[:19]} does not exist")
                continue
            approval, problem = found_entry
            if problem is not None:
                problems.append(f"{label}: approval {str(digest)[:19]} fails its re-check")
                continue
            if not any(isinstance(r, Mapping) and r.get("id") == old
                       and r.get("hash") == pinned
                       for r in approval.payload.get("records") or []):
                problems.append(f"{label}: approval {str(digest)[:19]} does not approve {old} "
                                "at the renumbered content; it carries nothing")
        record = index.get(new)
        if record is not None and record.hash == payload.get("new_hash") and \
                reverted_hash(record, _mapping(payload)) != pinned:
            problems.append(f"{label}: {new}'s content is not {old}'s with the new ID; "
                            "no approval is carried")
    return problems


def glance_rows(core: Any, known: set[str]) -> list[dict[str, Any]]:
    """Merge-boundary glance rows (R17): each renumber in the range that carries the
    owner's earlier ok, labelled "carried by renumber SR-070 -> SR-081"."""
    labels = carried(core)
    rows = []
    for entry in entries(core):
        new = entry.payload.get("to")
        if entry.digest in known or new not in labels:
            continue
        rows.append({"kind": "renumber", "by": "renumber", "at": entry.at,
                     "records": [new], "from": entry.payload.get("from"), "to": new,
                     "title": entry.payload.get("title") or "", "exempt": [],
                     "digest": entry.digest, "revoke": None})
    return rows
