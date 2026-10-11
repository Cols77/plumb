"""``plumb mod undo``: the Undo button on the settled line (sp7-realign-sp8 C6; SR-105 EX-1).

A record settled from the owner's words is taken back by its Undo button as by a typed
``/plumb undo``: a ``revocation {by: undone, via: button}`` of the record at its current
version, which ``recheck_settled`` accepts from the owner's panel (no session marker).
Refused (exit 3, nothing written) as every ``plumb mod`` command is: under the agent session
marker, without a registered panel, without the key or with another key. A record that is
not settled now changes nothing (exit 2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.mod.session import check_key
from plumb.present import owner_text


class NotSettled(LookupError):
    """The record is not settled now: nothing was written."""


def undo(core: Any, session: str, record_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    digest = check_key(core.root, session, payload, "undo")
    index = core.index()
    record = index.get(str(record_id).upper())
    state = core.status([record.id]).get(record.id) if record is not None else None
    if record is None or state is None or not state.settled:
        raise NotSettled(owner_text.UNDO_UNKNOWN.format(what=record_id))
    core.log_append("events", "revocation", {
        "records": [{"id": record.id, "hash": record.hash}], "by": "undone", "via": "button",
        "session": session, "key_digest": digest})
    return {"ok": True, "undone": [record.id], "line": owner_text.UNDO_DONE.format(
        title=record.title), "model_note": owner_text.PRESS_MODEL_UNDONE.format(
        records=f"{record.id} '{record.title}'")}
