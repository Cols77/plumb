"""The re-check of ``by: import`` approvals (next-plan 9.3).

Two levels, both deterministic:

- ``import_problem(entry)``: called by ``confirm.entry_problem`` for every approval or
  revocation entry ``by: import``, so a failing entry never confirms anything, in status,
  hooks, merge and validate alike. It needs no log context, so ``confirm.checked_entries``
  passes none and CAPTURE's re-checks there never share lines with this one. The entry must
  be an approval (only the owner revokes), written outside the agent session marker, right
  after the ``import`` event it cites (``prev`` equals ``import_event``), and carry a copy of
  that event (``import_entry``) whose digest is the cited one; that event must itself have
  been written outside the marker and have approved each record at the approved hash; and
  every record must cite its upstream consent: the consent file's path for that SR, its
  digest, the requirement digest the consent pinned, the run and the imported content's
  upstream hash.
- ``recheck_import_approvals(core)``: called by ``plumb validate``; the cited import event
  must be the log entry right before the approval, and a record still at the approved hash
  must still carry the upstream hash the consent matched.

The trust model is the concept's (4.6): tamper-evident, not tamper-proof against an agent
that forges both an import event and its approval.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

CONSENT_PATH = re.compile(r"^\.factory/planning/([A-Za-z0-9][A-Za-z0-9_.-]*)/consent/"
                          r"(SR-\d+)\.json$")
HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
RECORD_ID = re.compile(r"^SR-\d{3,}$")


def _item_problem(item: Any) -> str | None:
    if not isinstance(item, Mapping):
        return "a record entry is not a mapping"
    record_id = item.get("id")
    if not isinstance(record_id, str) or not RECORD_ID.match(record_id):
        return f"record {record_id!r} is not a requirement"
    if not isinstance(item.get("hash"), str) or not HASH.match(item["hash"]):
        return f"{record_id}: no pinned hash"
    upstream = item.get("upstream")
    if not isinstance(upstream, Mapping):
        return f"{record_id}: cites no upstream consent"
    match = CONSENT_PATH.match(str(upstream.get("consent_path") or ""))
    if match is None or match.group(2) != record_id or match.group(1) != upstream.get("run_id"):
        return f"{record_id}: cites no consent file of its own"
    if not HASH.match(str(upstream.get("consent_digest") or "")):
        return f"{record_id}: cites no consent digest"
    if not HEX.match(str(upstream.get("requirement_sha256") or "")):
        return f"{record_id}: cites no consented requirement digest"
    if not HASH.match(str(upstream.get("upstream_hash") or "")):
        return f"{record_id}: cites no upstream content hash"
    return None


def import_event_pairs(entry: Any) -> set[tuple[str, str]] | None:
    """The ``(id, hash)`` pairs an ``import`` event approved, or None when the event was
    written under the agent session marker (it then backs no approval)."""
    if entry.kind != "import" or entry.marker != "none":
        return None
    return {(str(a.get("id")), str(a.get("hash")))
            for a in entry.payload.get("approved") or [] if isinstance(a, Mapping)}


def event_copy(entry: Any) -> dict[str, Any]:
    """The copy of an ``import`` event its approval carries (``import_entry``)."""
    return {"at": entry.at, "marker": entry.marker, "payload": dict(entry.payload),
            "prev": entry.prev}


def carried_event(copy: Any, digest: str) -> Any:
    """The ``import`` event an approval carries, as a ``LogEntry``, or None when the copy is
    malformed or does not hash to ``digest``."""
    from plumb.contracts import LogEntry
    from plumb.log import entry_digest

    if not isinstance(copy, Mapping) or not isinstance(copy.get("payload"), Mapping):
        return None
    at, marker, prev = copy.get("at"), copy.get("marker"), copy.get("prev")
    if not isinstance(at, str) or not isinstance(marker, str) \
            or not (prev is None or isinstance(prev, str)):
        return None
    payload = dict(copy["payload"])
    if entry_digest({"v": 1, "kind": "import", "at": at, "marker": marker,
                     "payload": payload, "prev": prev}) != digest:
        return None
    return LogEntry(stream="events", kind="import", at=at, marker=marker, payload=payload,
                    prev=prev, digest=digest)


def import_problem(entry: Any) -> str | None:
    """Why a ``by: import`` log entry fails its re-check, or None.

    The guarantee: a ``by: import`` approval confirms only what an import run outside the
    agent session approved, after the owner answered its terminal question
    (``apply.apply_plan``). The approval carries the import event it cites, so the check
    needs nothing but the entry."""
    payload: Mapping[str, Any] = entry.payload
    if entry.kind != "approval":
        return f"import {entry.kind}: only the owner revokes"
    if entry.marker != "none":
        return f"by: import approval written under the agent session marker ({entry.marker})"
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return "import approval names no record"
    for item in records:
        problem = _item_problem(item)
        if problem:
            return f"import approval: {problem}"
    cited = payload.get("import_event")
    if not isinstance(cited, str) or entry.prev != cited:
        return "import approval not written right after the import event it cites"
    event = carried_event(payload.get("import_entry"), cited)
    if event is None:
        return "by: import approval carries no copy of the import event it cites"
    listed = import_event_pairs(event)
    if listed is None:
        return ("by: import approval cites an import event written under the agent session "
                f"marker ({event.marker})")
    for item in records:
        if (item["id"], item["hash"]) not in listed:
            return (f"{item['id']}: by: import approval pins a hash its import event did not "
                    "approve")
    return None


def recheck_import_approvals(core: Any) -> list[str]:
    """Problems of ``by: import`` approvals that depend on the log or the records' current
    state, as ``"<ID>: <problem>"`` lines (``plumb validate`` reports each as an error): the
    import event an approval carries must be the log entry right before it, and a record
    still at the approved hash must still carry the upstream hash the consent matched.
    Entries failing ``import_problem`` confirm nothing and are already reported through
    ``confirm.checked_entries``."""
    from plumb.confirm import checked_entries

    index = core.index()
    events = list(core.events())
    before = {e.digest: (events[i - 1] if i else None) for i, e in enumerate(events)}
    out: list[str] = []
    for entry, problem in checked_entries(events, core.config.approve.affirmations):
        if problem is not None or entry.kind != "approval" \
                or entry.payload.get("by") != "import":
            continue
        previous = before.get(entry.digest)
        if previous is None or previous.kind != "import" \
                or previous.digest != entry.payload["import_event"]:
            ids = ", ".join(str(r["id"]) for r in entry.payload["records"])
            out.append(f"{ids}: by: import approval's import event is not the log entry "
                       "right before it")
        for item in entry.payload["records"]:
            record_id, record_hash = item["id"], item["hash"]
            record = index.get(record_id)
            if record is None or record.hash != record_hash:
                continue  # edited since: it is an unconfirmed edit, nothing to re-check
            source = record.fields.get("source")
            upstream_hash = source.get("upstream_hash") if isinstance(source, Mapping) else None
            if upstream_hash != item["upstream"]["upstream_hash"]:
                out.append(f"{record_id}: by: import approval's upstream content does not "
                           "match the record's source")
    return out
