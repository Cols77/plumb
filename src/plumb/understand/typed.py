"""Typed commands (SR-101): an exact grammar, not reading.

``/plumb approve|confirm <IDs>``, ``/plumb undo <ID>``,
``/plumb auto-approve on|off`` and ``/plumb go`` are the owner's own exact actions. ``parse``
recognises them; a typed approve or confirm that names only IDs confirms at once
(``confirm_now``), recorded as passed on from the owner's typed command, the reader not called,
the record shown or not. A typed confirm with
words confirms nothing: the words go to the reader as prose. A typed auto-approve switches
automatic confirmation at once (``switch_now``, SR-115), logged as the owner's config event
exactly as the owner's terminal writes it; the same words inside a sentence switch nothing.
An undo of a record the judge or the owner's words confirmed is written at once (``undo_now``);
a typed go releases a failed check in ``clarify.on_prompt``. No command is run for any of
them and none carries a ``--prompt`` digest."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from plumb.present import owner_text

_ID = re.compile(r"^(?:(?:INT|SR|DEC|FEAT)-\d+|NC-\d+)$")
# SR-120: under the Claude Code plugin the command is namespaced, so the owner types /plumb or
# /plumb:plumb. Every parser of a typed command (here, clarify's go, the owner's auto-approve
# switch) starts with this one prefix and then whitespace, so
# /plumbing and /plumb:other never match.
PREFIX = r"/plumb(?::plumb)?"
_PREFIX_HEAD = re.compile(r"^" + PREFIX + r"(?=[ \t])")
_HEAD = re.compile(r"^" + PREFIX + r"[ \t]+([a-z][a-z-]*)(?:[ \t]+(.*))?$", re.DOTALL)


@dataclass(frozen=True)
class Typed:
    """A parsed typed command."""

    command: str          # approve | confirm | undo | auto-approve | go | settle | clarify | intent
    ids: tuple[str, ...] = ()          # the IDs it names (all of them, or none)
    words: str = ""                    # approve/confirm: what followed when it was not all IDs
    state: str = ""                    # auto-approve: on | off


@dataclass(frozen=True)
class TypedResult:
    confirmed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()


def canonical(text: str) -> str:
    """``text`` with a leading ``/plumb:plumb`` spelled ``/plumb`` (SR-120), else unchanged:
    what a check that compares the owner's message to an exact ``/plumb ...`` command (the
    typed undo) compares."""
    return _PREFIX_HEAD.sub("/plumb", text.lstrip(), count=1)


def parse(text: Any) -> Typed | None:
    """The typed command ``text`` is, or None. Exact: lower-case ``/plumb`` (or the plugin's
    ``/plumb:plumb``) first, the verb, then only what the verb takes."""
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
    if verb == "auto-approve" and len(tokens) == 1 and tokens[0] in ("on", "off"):
        return Typed("auto-approve", state=tokens[0])
    if verb == "go" and not tokens:
        return Typed("go")
    if verb in ("clarify", "intent") and rest:
        # SR-171, SR-193: the words are the request (intent also opens the loop)
        return Typed(verb, words=" ".join(rest.split()))
    if verb == "settle":
        return Typed("settle")             # SR-134 EX-2: the switch is gone, the words are not a request
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


def switch_now(core: Any, parsed: Typed, digest: str, session: str = "") -> TypedResult:
    """Switch automatic confirmation as the owner's typed ``/plumb auto-approve on|off`` says
    (SR-115, DEC-016): the command must be a prompt the prompt hook logged, word for word;
    the owner's ``config`` event is written as the terminal writes it, ``via: typed``."""
    from plumb.capture.jevcmd import auto_approve_typed
    from plumb.understand.read import logged_prompt

    if parsed.command != "auto-approve" or parsed.state not in ("on", "off"):
        return TypedResult()
    logged = logged_prompt(core, digest)
    if logged is None or logged.get("via") != "hook":
        return TypedResult()
    text = str(logged["text"])
    if parse(text) != parsed:
        return TypedResult()
    if digest not in {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}:
        core.log_append("events", "prompt", {"digest": digest,
                                             "session": logged.get("session") or session,
                                             "at": logged.get("at")})
    auto_approve_typed(core, parsed.state == "on", prompt_digest=digest, quote=text)
    return TypedResult(lines=(owner_text.AUTO_APPROVE_SWITCHED.format(state=parsed.state),))


def undo_now(core: Any, parsed: Typed, digest: str, session: str = "") -> TypedResult:
    """Take back the confirmation the judge or the owner's words gave the record a typed
    ``/plumb undo <ID>`` names, at once: the prompt must be one the hook logged, word for word;
    the record is proposed again (a ``revocation``, ``by: undone``, at its current version)."""
    from plumb.understand.read import logged_prompt

    if parsed.command != "undo" or not parsed.ids:
        return TypedResult()
    logged = logged_prompt(core, digest)
    if logged is None or logged.get("via") != "hook" or parse(str(logged["text"])) != parsed:
        return TypedResult()
    return take_back(core, parsed.ids[0], digest, logged, session)


def take_back(core: Any, record_id: str, digest: str = "", logged: Mapping[str, Any] | None = None,
              session: str = "") -> TypedResult:
    """The revocation of a confirmation plumb gave from the owner's words. Typed, it cites the
    logged prompt; from the owner's terminal (``plumb understand undo``) it cites none and
    ``problem`` accepts it only without the agent marker."""
    from plumb.normalize import normalize_text

    index = core.index()
    state = core.status([record_id]).get(record_id) if record_id in index else None
    if state is None or state.confirmation != "confirmed" or state.approved_by not in (
            "auto-jev", "owner-words", "auto-model"):
        return TypedResult(lines=(f"plumb: {record_id} was not confirmed by plumb reading your "
                                  "words; nothing changed.",))
    cited: dict[str, Any] = {}
    if logged is not None:
        if digest not in {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}:
            core.log_append("events", "prompt", {"digest": digest,
                                                 "session": logged.get("session") or session,
                                                 "at": logged.get("at")})
        cited = {"prompt_digest": digest, "quote": normalize_text(str(logged["text"]))}
    core.log_append("events", "revocation", {
        "records": [{"id": record_id, "hash": index[record_id].hash}], "by": "undone",
        "via": "typed", **cited})
    return TypedResult(confirmed=(record_id,), lines=(
        f"plumb: {index[record_id].title} is proposed again and waits for you.",))


def problem(entry: Any, core: Any) -> str | None:
    """Why an ``undone`` revocation fails its re-check, or None: the owner's own terminal (no
    agent marker), or the logged prompt of the owner's typed ``/plumb undo``."""
    from plumb.approvals import prompt_digest
    from plumb.normalize import sha256_text

    payload = entry.payload
    if entry.kind != "revocation":
        return f"undone {entry.kind}: only a revocation is undone"
    records = payload.get("records")
    if not isinstance(records, list) or not records or not all(
            isinstance(r, Mapping) and isinstance(r.get("id"), str) and r.get("hash")
            for r in records):
        return "undone revocation names no record at a version"
    if payload.get("via") != "typed":
        return "undone revocation was not typed"
    if entry.marker == "none":
        return None
    quote, digest = payload.get("quote"), payload.get("prompt_digest")
    parsed = parse(quote)
    if not isinstance(digest, str) or parsed is None or parsed.command != "undo" or digest not in (
            prompt_digest(quote), sha256_text(quote)):
        return "only you undo a record: type /plumb undo with its number"
    return None


def on_prompt(core: Any, entry: Any, session: str = "") -> list[str]:
    """What the prompt hook does for the typed commands that need no reading: an undo is done
    here."""
    if not isinstance(entry, Mapping):
        return []
    parsed = parse(entry.get("text"))
    if parsed is None:
        return []
    if parsed.command == "settle":
        return [owner_text.TYPED_SETTLE_GONE]
    if parsed.command == "undo":
        return list(undo_now(core, parsed, str(entry.get("digest") or ""), session).lines)
    return []
