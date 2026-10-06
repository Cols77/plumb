"""The re-check of ``by: import`` approvals (next-plan 9.3).

Two levels, both deterministic:

- ``import_problem(entry, imports)``: called by ``confirm.entry_problem`` (with the log
  context ``confirm.checked_entries`` builds) for every approval or revocation entry ``by:
  import``, so a failing entry never confirms anything, in status, hooks, merge and validate
  alike. The entry must be an approval (only the owner revokes), written outside the agent
  session marker, right after the ``import`` event it cites (``prev`` equals
  ``import_event``); that event must be an earlier ``import`` event, itself written outside
  the marker, that approved each record at the approved hash; and every record must cite its
  upstream consent: the consent file's path for that SR, its digest, the requirement digest
  the consent pinned, the run and the imported content's upstream hash.
- ``recheck_import_approvals(core)``: called by ``plumb validate``; a record still at the
  approved hash must still carry the upstream hash the consent matched.

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


def import_problem(entry: Any, imports: Mapping[str, set[tuple[str, str]]]) -> str | None:
    """Why a ``by: import`` log entry fails its re-check, or None.

    The guarantee: a ``by: import`` approval confirms only what an import run outside the
    agent session approved, after the owner answered its terminal question
    (``apply.apply_plan``). ``imports`` maps each earlier ``import`` event written outside the
    agent session to the ``(id, hash)`` pairs it approved (``import_event_pairs``)."""
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
    event = payload.get("import_event")
    if not isinstance(event, str) or entry.prev != event:
        return "import approval not written right after the import event it cites"
    listed = imports.get(event)
    if listed is None:
        return "by: import approval cites no earlier import event"
    for item in records:
        if (item["id"], item["hash"]) not in listed:
            return (f"{item['id']}: by: import approval pins a hash its import event did not "
                    "approve")
    return None


def recheck_import_approvals(core: Any) -> list[str]:
    """Problems of ``by: import`` approvals that depend on the records' current state, as
    ``"<ID>: <problem>"`` lines (``plumb validate`` reports each as an error): a record still
    at the approved hash must still carry the upstream hash the consent matched. Entries
    failing ``import_problem`` confirm nothing and are already reported through
    ``confirm.checked_entries``."""
    from plumb.confirm import checked_entries

    index = core.index()
    out: list[str] = []
    for entry, problem in checked_entries(core.events(), core.config.approve.affirmations):
        if problem is not None or entry.kind != "approval" \
                or entry.payload.get("by") != "import":
            continue
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
