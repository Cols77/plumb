"""SR-434, DEC-464: the owner's standing choice that the independent evaluator checks every
proof. Only the owner's logged ``config`` event switches it, written one of two ways, as
auto-approve's is (``ownerconfig``):

- ``iaso config evaluator always|ask`` in the owner's own terminal (``approvals.require_owner``);
- ``/iaso evaluator always|ask`` typed as a whole message and seen by the prompt hook, which
  writes the event ``via: typed`` with the command as its quote and the digest of that text.

Anything else (an event under the session marker without that proof, ``config.yaml``) changes
nothing; with no valid event the choice is off, the earlier rule."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from iaso.contracts import LogEntry
from iaso.understand.typed import PREFIX

if TYPE_CHECKING:
    from iaso.api import Core

KEY = "proof_evaluator"
ALWAYS, ASK = "always", "ask"
TYPED_VIA = "typed"
TYPED = re.compile(r"^" + PREFIX + r"[ \t]+evaluator[ \t]+(always|ask)$")


def _valid(entry: LogEntry, prompts: set[str], said: dict[str, str]) -> bool:
    from iaso.approvals import prompt_digest
    from iaso.normalize import sha256_text

    payload = entry.payload
    if entry.kind != "config" or payload.get("by") != "owner" or payload.get(KEY) not in (ALWAYS, ASK):
        return False
    if payload.get("via") != TYPED_VIA:
        return entry.marker == "none"             # the owner's terminal
    quote, digest = payload.get("quote"), payload.get("prompt_digest")
    if quote is None:
        quote = said.get(str(payload.get("quote_digest")))
    if not isinstance(quote, str) or not isinstance(digest, str):
        return False       # shortcut: words this clone lacks switch nothing (DEC-116); "off" could pass on the digest alone
    found = TYPED.match(quote.strip())
    return digest in (prompt_digest(quote), sha256_text(quote)) and digest in prompts \
        and found is not None and found.group(1) == payload[KEY]


def latest(entries: Sequence[LogEntry]) -> str | None:
    """The owner's latest valid choice, ``always`` or ``ask``, or None when they never switched."""
    prompts: set[str] = set()
    said: dict[str, str] = {}
    state: str | None = None
    for entry in entries:
        if entry.kind == "prompt" and isinstance(entry.payload.get("digest"), str):
            prompts.add(entry.payload["digest"])
        elif entry.kind == "owner-words" and isinstance(entry.payload.get("text"), str):
            said[str(entry.payload.get("digest"))] = entry.payload["text"]
        elif _valid(entry, prompts, said):
            state = str(entry.payload[KEY])
    return state


def always(core: Core) -> bool:
    return latest(core.events()) == ALWAYS


def set_terminal(core: Core, value: str) -> LogEntry:
    from iaso.approvals import require_owner

    require_owner("config evaluator", "have the independent evaluator check every proof, "
                  "without asking you each time?" if value == ALWAYS else
                  "go back to offering the evaluator at each proof question?")
    return core.log_append("events", "config", {KEY: value, "by": "owner"})


def set_typed(core: Core, value: str, *, prompt_digest: str, quote: str) -> LogEntry:
    return core.log_append("events", "config", {KEY: value, "by": "owner", "via": TYPED_VIA,
                                                "prompt_digest": prompt_digest, "quote": quote})
