"""Which ``config`` events are the owner's (DEC-016, SR-115), without the judgment modules.

Auto-approval is switched only by the owner's logged ``config`` event, written one of two ways:

- ``iaso config auto-approve on|off`` in the owner's own terminal: ``by: owner``, no session
  marker (``approvals.require_owner``);
- ``/iaso auto-approve on|off`` typed by the owner as a whole message and seen by the prompt
  hook: ``by: owner``, ``via: typed``, carrying the typed command as its quote and the digest
  of that very text, cited by a ``prompt`` event logged before it. The hook runs under the
  session marker, so the quote is the proof, as for a typed ``/iaso undo``.

Anything else (an event under the marker without that proof, a quote that says the other
state, ``config.yaml`` alone) switches nothing."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from iaso.contracts import LogEntry
from iaso.understand.typed import PREFIX

TYPED_VIA = "typed"
# SR-120: typed as /iaso or as the plugin's /iaso:iaso
TYPED = re.compile(r"^" + PREFIX + r"[ \t]+auto-approve\s+(on|off)$")

# where the owner's latest switch came from, in the owner's terms
SOURCE_TERMINAL = "your terminal"
SOURCE_TYPED = "your typed /iaso auto-approve {state}"


def _typed_digests(enabled: bool) -> set[str]:
    """The digests of the typed commands that say the state ``enabled``."""
    from iaso.normalize import sha256_text

    word = "on" if enabled else "off"
    return {sha256_text(f"{head} auto-approve {word}") for head in ("/iaso", "/iaso:iaso")}


def words_absent(entry: LogEntry, said: Mapping[str, str] | None = None) -> bool:
    """Whether ``entry`` was split from a quote this machine does not hold (DEC-116)."""
    payload = entry.payload
    digest = payload.get("quote_digest")
    return "quote" not in payload and isinstance(digest, str) \
        and digest not in (said or {})


def typed_proof(entry: LogEntry, said: Mapping[str, str] | None = None) -> bool:
    """Whether ``entry`` carries the owner's typed command saying the state it records.
    ``said`` is the local owner-words (digest -> text). A checkout without them accepts a
    recorded "off" on the structural check only (DEC-116): the digest must be that of a typed
    command saying off. A recorded "on" without the words is refused: auto-approve stays off."""
    from iaso.approvals import prompt_digest
    from iaso.normalize import sha256_text

    payload = entry.payload
    quote, digest = payload.get("quote"), payload.get("prompt_digest")
    settings = payload.get("auto_approve")
    if not isinstance(digest, str) or not isinstance(settings, Mapping):
        return False
    if quote is None and isinstance(payload.get("quote_digest"), str):
        quote = (said or {}).get(payload["quote_digest"])
        if quote is None:
            # owner, 2026-11-01: "on" needs the owner's words (a digest anyone can compute proves
            # nothing); "off" counts from the committed record alone
            return not settings.get("enabled") and payload["quote_digest"] in _typed_digests(False)
    if not isinstance(quote, str):
        return False
    if digest not in (prompt_digest(quote), sha256_text(quote)):
        return False
    found = TYPED.match(quote.strip())
    return found is not None and (found.group(1) == "on") == bool(settings.get("enabled"))


def owner_entries(entries: Sequence[LogEntry]) -> list[LogEntry]:
    """The owner's auto-approve ``config`` events in log order."""
    prompts: set[str] = set()
    said: dict[str, str] = {}
    out: list[LogEntry] = []
    for entry in entries:
        if entry.kind == "prompt":
            digest = entry.payload.get("digest")
            if isinstance(digest, str):
                prompts.add(digest)
        elif entry.kind == "owner-words":
            if isinstance(entry.payload.get("text"), str):
                said[str(entry.payload.get("digest"))] = entry.payload["text"]
        elif is_owner_config(entry, prompts, said):
            out.append(entry)
    return out


def is_owner_config(entry: LogEntry, prompts: set[str],
                    said: Mapping[str, str] | None = None) -> bool:
    """``owner_entries`` for one entry, given the prompt digests and the owner-words logged
    before it."""
    payload = entry.payload
    if entry.kind != "config" or payload.get("by") != "owner" \
            or not isinstance(payload.get("auto_approve"), Mapping):
        return False
    if payload.get("via") == TYPED_VIA:
        if words_absent(entry, said):   # DEC-116: not re-checked against words not here
            return typed_proof(entry, said)
        return payload.get("prompt_digest") in prompts and typed_proof(entry, said)
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
