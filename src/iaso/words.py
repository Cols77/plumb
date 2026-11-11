"""The owner's text beside the entries that were split from it (DEC-116, DEC-232).

A shared entry (approval, revocation, conflict-resolution, waiver) is committed with the
outcome and ``<field>_digest`` in place of the text the owner typed; the text is a local
``owner-words`` entry. ``joined`` gives an entry's payload with the text put back where this
machine has it, and without it where it does not: a reader never fails for want of words.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from iaso.log import OWNER_TEXT_FIELDS


def held(core: Any) -> dict[str, Any]:
    """Digest -> the text of every ``owner-words`` entry this machine can read."""
    return {str(e.payload.get("digest")): e.payload.get("text")
            for e in core.events() if e.kind == "owner-words"}


def joined(core: Any, entry: Any, said: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``entry``'s payload with its split fields put back from ``said`` (``held(core)``)."""
    payload = dict(entry.payload)
    fields = OWNER_TEXT_FIELDS.get(entry.kind, ())
    if not any(f"{f}_digest" in payload and f not in payload for f in fields):
        return payload
    said = held(core) if said is None else said
    for field in fields:
        digest = payload.get(f"{field}_digest")
        if field not in payload and digest in said:
            payload[field] = said[str(digest)]
    return payload


def unavailable(core: Any, entry: Any) -> bool:
    """Whether ``entry`` was split from text this machine does not hold: its outcome stands and
    nothing is re-checked against words that are not here (DEC-116)."""
    joined_ = joined(core, entry) if core is not None else dict(entry.payload)
    return any(f"{f}_digest" in joined_ and f not in joined_
               for f in OWNER_TEXT_FIELDS.get(entry.kind, ()))
