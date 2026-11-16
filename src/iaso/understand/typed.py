"""Typed commands (SR-101): an exact grammar, not reading.

``/iaso undo <ID>``, ``/iaso auto-approve on|off`` and ``/iaso go`` are the owner's own
exact actions. ``parse`` recognises them. ``/iaso approve|confirm`` is no longer a command
(SR-209 EX-6): ``parse`` returns None, nothing is approved and the words go to the reader as
prose; ``legacy_ids`` reads a past typed approval only to re-check it. A typed auto-approve
switches automatic confirmation at once (``switch_now``, SR-115), logged as the owner's config event
exactly as the owner's terminal writes it; the same words inside a sentence switch nothing.
An undo of a record the judge or the owner's words confirmed is written at once (``undo_now``);
a typed go releases a failed check in ``clarify.on_prompt``. No command is run for any of
them and none carries a ``--prompt`` digest."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from iaso.present import owner_text

_ID = re.compile(r"^(?:(?:INT|SR|DEC|FEAT)-\d+|NC-\d+)$")
# SR-120: under the Claude Code plugin the command is namespaced, so the owner types /iaso or
# /iaso:iaso. Every parser of a typed command (here, clarify's go, the owner's auto-approve
# switch) starts with this one prefix and then whitespace, so
# /wiring and /iaso:other never match.
PREFIX = r"/iaso(?::iaso)?"
_PREFIX_HEAD = re.compile(r"^" + PREFIX + r"(?=[ \t])")
_HEAD = re.compile(r"^" + PREFIX + r"[ \t]+([a-z][a-z-]*)(?:[ \t]+(.*))?$", re.DOTALL)
# the plugin's skills answer to /iaso:iaso-intent and /iaso:iaso-clarify: the same commands
_SKILL_SPELLING = re.compile(r"^/iaso:iaso-(intent|clarify)(?=[ \t])")
# SR-304: a pasted command arrives wrapped as <pasted_content ...>body</pasted_content ...>
_PASTE = re.compile(r"^<pasted_content\b[^>]*>(.*?)</pasted_content\b[^>]*>(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Typed:
    """A parsed typed command."""

    command: str          # undo | auto-approve | evaluator | go | settle | clarify | intent
    ids: tuple[str, ...] = ()          # undo: the ID it names
    words: str = ""                    # clarify/intent: the request
    state: str = ""                    # auto-approve: on | off


@dataclass(frozen=True)
class TypedResult:
    confirmed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()


def canonical(text: str) -> str:
    """``text`` with a leading ``/iaso:iaso`` spelled ``/iaso`` (SR-120), else unchanged:
    what a check that compares the owner's message to an exact ``/iaso ...`` command (the
    typed undo) compares."""
    return _PREFIX_HEAD.sub("/iaso", text.lstrip(), count=1)


def parse(text: Any) -> Typed | None:
    """The typed command ``text`` is, or None. Exact: lower-case ``/iaso`` (or the plugin's
    ``/iaso:iaso``) first, the verb, then only what the verb takes."""
    if not isinstance(text, str):
        return None
    text = _SKILL_SPELLING.sub(r"/iaso \1", text.strip())
    pasted = _PASTE.match(text)
    if pasted is not None:
        # SR-304: only a pasted intent or clarify is the command; the owner's words follow it
        text = f"{pasted.group(1).strip()} {pasted.group(2).strip()}".strip()
        text = _SKILL_SPELLING.sub(r"/iaso \1", text)
        if not re.match(r"^" + PREFIX + r"[ \t]+(?:intent|clarify)\b", text):
            return None
    match = _HEAD.match(text)
    if match is None:
        return None
    verb, rest = match.group(1), (match.group(2) or "").strip()
    tokens = rest.split()
    if verb == "undo" and len(tokens) == 1 and _ID.match(tokens[0]):
        return Typed("undo", tuple(tokens))
    if verb == "auto-approve" and len(tokens) == 1 and tokens[0] in ("on", "off"):
        return Typed("auto-approve", state=tokens[0])
    if verb == "evaluator" and len(tokens) == 1 and tokens[0] in ("always", "ask"):
        return Typed("evaluator", state=tokens[0])    # SR-434
    if verb == "go" and not tokens:
        return Typed("go")
    if verb in ("clarify", "intent") and rest:
        # SR-171, SR-193: the words are the request (intent also opens the loop)
        return Typed(verb, words=" ".join(rest.split()))
    if verb == "settle":
        return Typed("settle")             # SR-134 EX-2: the switch is gone, the words are not a request
    return None


def legacy_ids(text: Any) -> tuple[str, ...] | None:
    """The IDs a past typed ``/iaso approve|confirm <IDs>`` named, or None: read only to
    re-check an approval logged before the command went (``confirm.py``); it approves nothing."""
    match = _HEAD.match(text.strip()) if isinstance(text, str) else None
    if match is None or match.group(1) not in ("approve", "confirm"):
        return None
    tokens = [t for t in re.split(r"[\s,]+", (match.group(2) or "").strip()) if t]
    return tuple(tokens) if tokens and all(_ID.match(t) for t in tokens) else None


def switch_now(core: Any, parsed: Typed, digest: str, session: str = "") -> TypedResult:
    """Switch automatic confirmation as the owner's typed ``/iaso auto-approve on|off`` says
    (SR-115, DEC-016): the command must be a prompt the prompt hook logged, word for word;
    the owner's ``config`` event is written as the terminal writes it, ``via: typed``."""
    from iaso.capture.jevcmd import auto_approve_typed
    from iaso.understand.read import logged_prompt

    if parsed.command == "evaluator" and parsed.state in ("always", "ask"):
        return _switch_evaluator(core, parsed, digest, session)    # SR-434
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


def _switch_evaluator(core: Any, parsed: Typed, digest: str, session: str) -> TypedResult:
    """The owner's typed ``/iaso evaluator always|ask`` (SR-434): the same checks as the typed
    auto-approve switch, then the owner's ``config`` event, ``via: typed``."""
    from iaso.capture import evaluatorpref
    from iaso.understand.read import logged_prompt

    logged = logged_prompt(core, digest)
    if logged is None or logged.get("via") != "hook" or parse(str(logged["text"])) != parsed:
        return TypedResult()
    if digest not in {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}:
        core.log_append("events", "prompt", {"digest": digest,
                                             "session": logged.get("session") or session,
                                             "at": logged.get("at")})
    evaluatorpref.set_typed(core, parsed.state, prompt_digest=digest, quote=str(logged["text"]))
    return TypedResult(lines=(owner_text.EVALUATOR_SWITCHED[parsed.state],))


def undo_now(core: Any, parsed: Typed, digest: str, session: str = "") -> TypedResult:
    """Take back the confirmation the judge or the owner's words gave the record a typed
    ``/iaso undo <ID>`` names, at once: the prompt must be one the hook logged, word for word;
    the record is proposed again (a ``revocation``, ``by: undone``, at its current version)."""
    from iaso.understand.read import logged_prompt

    if parsed.command != "undo" or not parsed.ids:
        return TypedResult()
    logged = logged_prompt(core, digest)
    if logged is None or logged.get("via") != "hook" or parse(str(logged["text"])) != parsed:
        return TypedResult()
    return take_back(core, parsed.ids[0], digest, logged, session)


def take_back(core: Any, record_id: str, digest: str = "", logged: Mapping[str, Any] | None = None,
              session: str = "") -> TypedResult:
    """The revocation of a confirmation iaso gave from the owner's words. Typed, it cites the
    logged prompt; from the owner's terminal (``iaso understand undo``) it cites none and
    ``problem`` accepts it only without the agent marker."""
    from iaso.normalize import normalize_text

    index = core.index()
    state = core.status([record_id]).get(record_id) if record_id in index else None
    if state is None or state.confirmation != "confirmed" or state.approved_by not in (
            "auto-jev", "owner-words", "auto-model"):
        return TypedResult(lines=(f"iaso: {record_id} was not confirmed by iaso reading your "
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
        f"iaso: {index[record_id].title} is proposed again and waits for you.",))


def problem(entry: Any, core: Any) -> str | None:
    """Why an ``undone`` revocation fails its re-check, or None: the owner's own terminal (no
    agent marker), or the logged prompt of the owner's typed ``/iaso undo``."""
    from iaso.approvals import prompt_digest
    from iaso.normalize import sha256_text

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
        return "only you undo a record: type /iaso undo with its number"
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
