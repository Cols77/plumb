"""``/plumb settle on|off [intent|requirement]`` and ``/plumb undo <title or ID>`` (JUDGE).

Both are the owner's alone (SR-041, SR-105 EX-6, SR-106 EX-4): switching settling and taking a
settled record back change only by the owner's typed command or a button, never by a model's
reading of prose and never by the agent on its own. Two ways in:

- the owner's own terminal: ``plumb settle on intent`` answered ``y`` at the terminal question
  (``approvals.require_owner``: refused under the agent session marker and in any shell that is
  not an interactive terminal);
- the owner's typed command in the chat: the agent runs the command with ``--prompt <digest>``
  of the owner's logged message, which must be exactly that command (``/plumb settle on
  intent``) and nothing else. A message in prose ("turn settling on") is refused, and the reply
  names the command and the button.

What is written carries its proof: the typed command and its digest, so the re-check can tell
the owner's entry from a forged one."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from plumb.cliutil import EXIT_OK, EXIT_REFUSED, EXIT_USAGE, add_common, resolve_root
from plumb.present import owner_text
from plumb.understand import settle

_ID = re.compile(r"^(?:INT|SR|DEC|FEAT)-\d{3,}$", re.IGNORECASE)


class Refusal(Exception):
    """The owner's command was not given as the owner: nothing was written."""


def _normalized(text: str) -> str:
    return " ".join(str(text).split()).lower()


def _record_prompt(core: Any, prompt: Any) -> None:
    """Log the prompt event the typed command rests on (once), as ``plumb relay`` does."""
    digest = str(prompt["digest"])
    if not any(e.kind == "prompt" and e.payload.get("digest") == digest for e in core.events()):
        core.log_append("events", "prompt", {"digest": digest, "session": prompt.get("session"),
                                             "at": prompt.get("at")})


def _authorize(core: Any, prompt_digest: str | None, command_text: str, name: str,
               refusal_prose: str, refusal_agent: str) -> dict[str, Any]:
    """The proof of an owner-only command, or ``Refusal``: the owner's typed command (the
    logged prompt is exactly ``command_text``) or their own terminal."""
    from plumb.approvals import Declined, Refused, find_prompt, require_owner

    if prompt_digest:
        try:
            prompt = find_prompt(core, prompt_digest)
        except Refused as exc:
            raise Refusal(str(exc)) from exc
        text = " ".join(str(prompt["text"]).split())
        if prompt.get("via") != "hook" or _normalized(text) != _normalized(command_text):
            raise Refusal(refusal_prose)
        _record_prompt(core, prompt)
        return {"via": "typed", "prompt_digest": str(prompt["digest"]), "quote": text}
    try:
        require_owner(name, f"{command_text} ?")
    except Declined as exc:
        raise Refusal(str(exc)) from exc
    except Refused as exc:
        raise Refusal(refusal_agent) from exc
    return {"via": "typed"}


# --------------------------------------------------------------------------- settle


def _latest_calibration(core: Any, kind: str) -> str:
    found = settle.judge_calibration(core.events(), kind)
    return found.digest if found is not None else ""


def _settle(core: Any, words: Sequence[str], prompt: str | None) -> int:
    if not words or words[0].lower() not in ("on", "off"):
        for kind in settle.KINDS:
            state = "on" if settle.state(core, kind).on else "off"
            print(owner_text.SETTLE_STATE_LINE.format(kind=kind, state=state))
        return EXIT_OK
    word, kinds = words[0].lower(), [k.lower() for k in words[1:]]
    if any(k not in settle.KINDS for k in kinds):
        print(f"plumb: settle {word}: say intent or requirement", file=sys.stderr)
        return EXIT_USAGE
    command = " ".join(["/plumb", "settle", word, *kinds])
    shown_kind = kinds[0] if kinds else settle.KINDS[0]
    try:
        proof = _authorize(
            core, prompt, command, "settle",
            owner_text.SETTLE_REFUSED_PROSE.format(state=word, kind=shown_kind),
            owner_text.SETTLE_REFUSED_AGENT.format(state=word, kind=shown_kind))
    except Refusal as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    on = word == "on"
    for kind in kinds or settle.KINDS:
        if settle.owner_latest(core, kind) is on:
            print(owner_text.SETTLE_STATE_LINE.format(kind=kind, state=word))
            continue
        core.log_append("events", "settle-config", {
            "kind": kind, "on": on, "calibration": _latest_calibration(core, kind), **proof})
        print(owner_text.SETTLE_SWITCHED.format(kind=kind, state=word))
    return EXIT_OK


# --------------------------------------------------------------------------- undo


def _settled_titles(core: Any) -> dict[str, Any]:
    index = core.index()
    return {rid: index[rid] for rid, status in core.status().items() if status.settled}


def resolve(core: Any, words: Sequence[str]) -> list[Any]:
    """The settled records ``words`` name: record numbers, or one title (case ignored)."""
    settled = _settled_titles(core)
    ids = [w.strip(",;").upper() for w in words if _ID.match(w.strip(",;"))]
    if ids and len(ids) == len(words):
        return [settled[i] for i in ids if i in settled]
    wanted = _normalized(" ".join(words))
    return [r for r in settled.values() if _normalized(r.title) == wanted]


def _undo(core: Any, words: Sequence[str], prompt: str | None) -> int:
    if not words:
        print(f"plumb: undo: {owner_text.UNDO_REFUSED}", file=sys.stderr)
        return EXIT_USAGE
    command = " ".join(["/plumb", "undo", *words])
    try:
        proof = _authorize(core, prompt, command, "undo", owner_text.UNDO_REFUSED,
                           owner_text.UNDO_REFUSED)
    except Refusal as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    found = resolve(core, words)
    if not found:
        print(owner_text.UNDO_UNKNOWN.format(what=" ".join(words)))
        return EXIT_USAGE
    core.log_append("events", "revocation", {
        "records": [{"id": r.id, "hash": r.hash} for r in found], "by": "undone", **proof})
    for record in found:
        print(owner_text.UNDO_DONE.format(title=record.title))
    return EXIT_OK


# --------------------------------------------------------------------------- entry point


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"plumb {command}")
    add_common(parser)
    parser.add_argument("--prompt", default=None,
                        help="digest of the owner's logged message that is the typed command")
    parser.add_argument("words", nargs="*")
    args = parser.parse_args(argv)
    from plumb.api import open_core

    core = open_core(Path(resolve_root(args.root)))
    if command == "undo":
        return _undo(core, args.words, args.prompt)
    return _settle(core, args.words, args.prompt)
