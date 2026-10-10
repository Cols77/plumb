"""The proof of an owner's typed command is used once, in the turn it was typed.

A typed ``/plumb settle on intent`` (or ``undo``, ``go``) is the owner's word only for the moment
they said it. The prompt log keeps every message, and the same words share a digest, so a digest
alone could be replayed by the agent long after: after the owner switched settling off, after
they took an undo back, or for a failed check that came later. Three checks, none of which read
the owner's words:

- the message is the latest one the prompt hook logged for its session, when the agent presents
  it (the owner's own terminal needs no proof);
- the message has not been used: each entry written on a typed proof carries the position of
  the message in the log (``prompt_seq``), and a second use of that position is refused;
- nothing the owner did by a button or in their terminal since that message has changed the
  same thing (``superseded``)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

# the log entries a typed proof is written into
PROOF_KINDS = ("settle-config", "revocation", "gate")


def _lines(core: Any) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    try:
        with open(core.paths.prompts, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, Mapping):
                    out.append(item)
    except OSError:
        pass
    return out


def seq_of(core: Any, digest: str) -> int:
    """The position in the prompt log of the latest message with ``digest``, or -1."""
    found = -1
    for n, item in enumerate(_lines(core)):
        if item.get("digest") == digest:
            found = n
    return found


def is_current_turn(core: Any, digest: str) -> bool:
    """Whether the message is the latest one the prompt hook logged for its own session."""
    entries = _lines(core)
    seq = seq_of(core, digest)
    if seq < 0:
        return False
    session = entries[seq].get("session")
    latest = max((n for n, item in enumerate(entries)
                  if item.get("via") == "hook" and item.get("session") == session), default=-1)
    return seq == latest


def used(core: Any, digest: str, seq: int) -> bool:
    """Whether an entry already rests on this very message (same digest, same position)."""
    return any(e.kind in PROOF_KINDS and e.payload.get("prompt_digest") == digest
               and e.payload.get("prompt_seq") == seq for e in core.events())


def superseded(core: Any, kinds: Iterable[str], prompt_at: str, *, subject: Iterable[str] = (),
               key: str = "kind", via: Iterable[str] = ()) -> bool:
    """Whether the owner changed the same thing since the message, without a typed proof (a
    button, or their own terminal): an entry of ``kinds`` naming ``subject`` (by ``key``) that
    carries no prompt and was written after the message (``via``: only those the owner wrote)."""
    wanted, owner = set(subject), set(via)
    for entry in core.events():
        if entry.kind not in kinds or entry.payload.get("prompt_digest"):
            continue
        if owner and entry.payload.get("via") not in owner:
            continue
        if wanted and not _names(entry.payload, key, wanted):
            continue
        if entry.at > prompt_at:
            return True
    return False


def _names(payload: Mapping[str, Any], key: str, wanted: set[str]) -> bool:
    if key == "records":
        return any(isinstance(r, Mapping) and str(r.get("id")) in wanted
                   for r in payload.get("records") or ())
    return str(payload.get(key)) in wanted
