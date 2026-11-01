"""Re-check of ``by: owner-words`` approvals (READ).

An owner-words approval is written by the worker only (the log checks the token when it is
written); this re-check is what makes a forged or altered entry confirm nothing afterwards.
It is self-contained: the entry carries the message it rests on, so the check needs no log
context. The caller (``confirm.entry_problem``) has already checked that the prompt digest is
one of the logged prompt events; with a ``core`` this also compares the message with the prompt
log's own text."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import LogEntry
from plumb.present.owner_text import NOT_AVAILABLE


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why an owner-words entry fails its re-check, or None."""
    from plumb.approvals import prompt_digest
    from plumb.normalize import sha256_text
    from plumb.understand.read import evidence_in

    payload: Mapping[str, Any] = entry.payload
    if not any(payload.get(k) for k in ("job", "prompt_digest", "evidence", "message")):
        return NOT_AVAILABLE   # not shaped by the worker at all: never accepted
    if entry.kind not in ("approval", "revocation"):   # SR-372 EX-6: a reversal in words
        return f"owner-words {entry.kind}: only approvals and revocations rest on their words"
    records = payload.get("records")
    if not isinstance(records, list) or not all(
            isinstance(r, Mapping) and isinstance(r.get("id"), str) and r.get("hash")
            for r in records):
        return f"owner-words {entry.kind} names no record at a version"
    digest, message, evidence = (payload.get("prompt_digest"), payload.get("message"),
                                 payload.get("evidence"))
    if not isinstance(digest, str) or not digest:
        return f"owner-words {entry.kind} cites no prompt"
    if not isinstance(message, str) or digest not in (prompt_digest(message),
                                                      sha256_text(message)):
        return "owner-words approval carries a message that is not the prompt it cites"
    if not isinstance(evidence, str) or not evidence_in(evidence, message):
        return "owner-words approval quotes words that are not in the message"
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) \
            or not 0 <= confidence <= 1:
        return "owner-words approval carries no confidence from 0 to 1"
    if not isinstance(payload.get("job"), str) or not payload["job"]:
        return "owner-words approval names no read job"
    if core is not None:
        from plumb.understand.read import logged_prompt

        logged = logged_prompt(core, digest)
        if logged is None or logged.get("text") != message:
            return "owner-words approval cites a prompt that is not in the prompt log"
    return None
