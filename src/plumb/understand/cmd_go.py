"""``plumb go --prompt <digest>`` (SHOW S3): the owner's typed ``/plumb go`` releases a failed
check, so edits are allowed again without it.

The command takes the digest of the owner's logged message and opens the gate only when that
logged message is exactly the typed ``/plumb go``, written by the host's prompt hook. The agent
cannot run it for itself: with the session marker set it is refused (exit 3) and nothing is
written. The prompt hook does the same release itself when it logs a typed ``/plumb go``, which
is the usual way."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from plumb.present.owner_text import NOT_AVAILABLE
from plumb.understand import clarify, gate, proof

EXIT_NOTHING = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3
NOTHING_TO_RELEASE = "Nothing is waiting for you to say build anyway."
REFUSED_AGENT = ("Only the owner can say to build without the check; this was refused and "
                 "nothing changed.")
REFUSED_OLD = ("That typed go is older than the check that failed, or was already used; type go "
               "again to build without the check.")
REFUSED_NOT_TYPED = ("The message with that digest is not exactly the typed go; nothing "
                     "changed.")


def release(core: Any, digest: str) -> tuple[int, str]:
    """``(exit code, message)`` of releasing the failed check with the logged message
    ``digest``; writes only when the code is 0."""
    from plumb.approvals import Refused, find_prompt, marker

    if marker():
        return EXIT_REFUSED, REFUSED_AGENT
    try:
        entry = find_prompt(core, digest)
    except Refused:
        return EXIT_REFUSED, REFUSED_NOT_TYPED
    if entry.get("via") != "hook" or not clarify.is_typed_go(str(entry.get("text") or "")):
        return EXIT_REFUSED, REFUSED_NOT_TYPED
    session = str(entry.get("session") or "")
    seq = proof.seq_of(core, str(entry["digest"]))
    if session and gate.failed_check_open(core.root, session) and (
            gate.typed_is_late(core, session, seq) or proof.used(core, str(entry["digest"]), seq)):
        return EXIT_REFUSED, REFUSED_OLD
    if session and gate.release(core, session, "typed", digest=str(entry["digest"]),
                                prompt_seq=seq):
        return 0, clarify.GATE_RELEASED
    return EXIT_NOTHING, NOTHING_TO_RELEASE


def run(command: str, argv: list[str]) -> int:
    from plumb.cliutil import add_common, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Build without the check, after the owner typed go.")
    add_common(parser)
    parser.add_argument("--prompt", default=None, help="the digest of the owner's typed message")
    args = parser.parse_args(argv)
    if not args.prompt:
        print(f"plumb: go: {NOT_AVAILABLE} without the digest of the owner's typed message; "
              "the part that is: plumb go --prompt DIGEST", file=sys.stderr)
        return EXIT_USAGE
    from plumb.api import open_core

    core = open_core(Path(resolve_root(args.root)))
    code, message = release(core, str(args.prompt))
    print(message, file=sys.stderr if code else sys.stdout)
    return code
