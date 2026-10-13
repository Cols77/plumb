"""Which ``config`` events are the owner's (DEC-016, SR-115), without the judgment modules.

Auto-approval is switched only by the owner's logged ``config`` event, written one of two ways:

- ``plumb config auto-approve on|off`` in the owner's own terminal: ``by: owner``, no session
  marker (``approvals.require_owner``);
- ``/plumb auto-approve on|off`` typed by the owner as a whole message and seen by the prompt
  hook: ``by: owner``, ``via: typed``, carrying the typed command as its quote and the digest
  of that very text, cited by a ``prompt`` event logged before it. The hook runs under the
  session marker, so the quote is the proof, as for a typed ``/plumb undo``.

Anything else (an event under the marker without that proof, a quote that says the other
state, ``config.yaml`` alone) switches nothing."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from plumb.contracts import LogEntry
from plumb.understand.typed import PREFIX

TYPED_VIA = "typed"
# SR-120: typed as /plumb or as the plugin's /plumb:plumb
TYPED = re.compile(r"^" + PREFIX + r"[ \t]+auto-approve\s+(on|off)$")

# where the owner's latest switch came from, in the owner's terms
SOURCE_TERMINAL = "your terminal"
SOURCE_TYPED = "your typed /plumb auto-approve {state}"


def typed_proof(entry: LogEntry) -> bool:
    """Whether ``entry`` carries the owner's typed command saying the state it records."""
    from plumb.approvals import prompt_digest
    from plumb.normalize import sha256_text

    payload = entry.payload
    quote, digest = payload.get("quote"), payload.get("prompt_digest")
    settings = payload.get("auto_approve")
    if not isinstance(quote, str) or not isinstance(digest, str) \
            or not isinstance(settings, Mapping):
        return False
    if digest not in (prompt_digest(quote), sha256_text(quote)):
        return False
    found = TYPED.match(quote.strip())
    return found is not None and (found.group(1) == "on") == bool(settings.get("enabled"))


def owner_entries(entries: Sequence[LogEntry]) -> list[LogEntry]:
    """The owner's auto-approve ``config`` events in log order."""
    prompts: set[str] = set()
    out: list[LogEntry] = []
    for entry in entries:
        if entry.kind == "prompt":
            digest = entry.payload.get("digest")
            if isinstance(digest, str):
                prompts.add(digest)
        elif is_owner_config(entry, prompts):
            out.append(entry)
    return out


def is_owner_config(entry: LogEntry, prompts: set[str]) -> bool:
    """``owner_entries`` for one entry, given the prompt digests logged before it."""
    payload = entry.payload
    if entry.kind != "config" or payload.get("by") != "owner" \
            or not isinstance(payload.get("auto_approve"), Mapping):
        return False
    if payload.get("via") == TYPED_VIA:
        return payload.get("prompt_digest") in prompts and typed_proof(entry)
    return entry.marker == "none"


def latest(entries: Sequence[LogEntry]) -> LogEntry | None:
    """The owner's latest auto-approve ``config`` event, or None."""
    found = owner_entries(entries)
    return found[-1] if found else None


def source_of(entry: LogEntry | None) -> str | None:
    """Where the owner's switch came from, in their terms; None when they never switched."""
    if entry is None:
        return None
    if entry.payload.get("via") == TYPED_VIA:
        on = bool(entry.payload["auto_approve"].get("enabled"))
        return SOURCE_TYPED.format(state="on" if on else "off")
    return SOURCE_TERMINAL
