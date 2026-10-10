"""Typed commands (SR-101): an exact grammar, not reading.

``/plumb approve|confirm <IDs>``, ``/plumb undo <ID>``, ``/plumb settle on|off <kind>`` and
``/plumb go`` are the owner's own exact actions. ``parse`` recognises them; a typed approve or
confirm that names only IDs confirms at once (``confirm_now``), recorded as passed on from the
owner's typed command, the reader not called, the record shown or not. A typed confirm with
words confirms nothing: the words go to the reader as prose. Undo, settle and go are carried
out by their own commands (with the prompt digest), never by this module."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from plumb.present import owner_text

_ID = re.compile(r"^(?:(?:INT|SR|DEC|FEAT)-\d+|NC-\d+)$")
_KIND = re.compile(r"^[a-z][a-z-]*$")
_HEAD = re.compile(r"^/plumb[ \t]+([a-z]+)(?:[ \t]+(.*))?$", re.DOTALL)


@dataclass(frozen=True)
class Typed:
    """A parsed typed command."""

    command: str                       # approve | confirm | undo | settle | go
    ids: tuple[str, ...] = ()          # the IDs it names (all of them, or none)
    words: str = ""                    # approve/confirm: what followed when it was not all IDs
    state: str = ""                    # settle: on | off
    kind: str = ""                     # settle: the record kind


@dataclass(frozen=True)
class TypedResult:
    confirmed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()


def parse(text: Any) -> Typed | None:
    """The typed command ``text`` is, or None. Exact: lower-case ``/plumb`` first, the verb,
    then only what the verb takes."""
    if not isinstance(text, str):
        return None
    match = _HEAD.match(text.strip())
    if match is None:
        return None
    verb, rest = match.group(1), (match.group(2) or "").strip()
    if verb in ("approve", "confirm"):
        tokens = [t for t in re.split(r"[\s,]+", rest) if t]
        if tokens and all(_ID.match(t) for t in tokens):
            return Typed(verb, tuple(dict.fromkeys(tokens)))
        return Typed(verb, words=" ".join(rest.split()))
    tokens = rest.split()
    if verb == "undo" and len(tokens) == 1 and _ID.match(tokens[0]):
        return Typed("undo", tuple(tokens))
    if verb == "settle" and len(tokens) == 2 and tokens[0] in ("on", "off") \
            and _KIND.match(tokens[1]):
        return Typed("settle", state=tokens[0], kind=tokens[1])
    if verb == "go" and not tokens:
        return Typed("go")
    return None


def reply_for(parsed: Typed) -> str | None:
    """What the owner is told about a typed command that confirms nothing by itself."""
    if parsed.command in ("approve", "confirm") and not parsed.ids:
        return owner_text.TYPED_NEEDS_IDS
    return None


def confirm_now(core: Any, parsed: Typed, digest: str, session: str = "") -> TypedResult:
    """Confirm the IDs a typed approve or confirm names, at once, as passed on from the
    owner's typed command. The command must be a prompt the prompt hook logged, word for
    word; the records are confirmed at their current version, shown or not."""
    from plumb.approvals import approval_items
    from plumb.normalize import normalize_text, sha256_text
    from plumb.understand.read import logged_prompt

    if parsed.command not in ("approve", "confirm") or not parsed.ids:
        return TypedResult()
    logged = logged_prompt(core, digest)
    if logged is None or logged.get("via") != "hook":
        return TypedResult()
    text = str(logged["text"])
    if parse(text) != parsed:
        return TypedResult()
    index = core.index()
    present = [i for i in parsed.ids if i in index]
    missing = tuple(i for i in parsed.ids if i not in index)
    current = core.status(present)
    todo = [i for i in present if current[i].confirmation != "confirmed"]
    if todo:
        quote = normalize_text(text)
        if digest not in {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}:
            core.log_append("events", "prompt", {"digest": digest,
                                                 "session": logged.get("session") or session,
                                                 "at": logged.get("at")})
        core.log_append("events", "approval", {
            "records": approval_items(core, todo), "by": "agent-relayed", "via": "command",
            "prompt_digest": digest, "quote": quote, "quote_digest": sha256_text(quote),
            "self_recorded": False, "affirmation": parsed.command, "stated_set": None,
            "note": ""})
    titles = ", ".join(index[i].title for i in present)
    lines = (owner_text.TYPED_CONFIRMED.format(titles=titles),) if present else ()
    return TypedResult(confirmed=tuple(present), missing=missing, lines=lines)
