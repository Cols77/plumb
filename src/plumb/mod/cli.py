"""``plumb mod hello|draw|press``: the commands only plumb's panel (the Claude Code mod)
runs.

All of them take ``--session <id>`` and read one JSON object on stdin; none takes a key in argv.

- ``hello``  stdin ``{"key_digest": "<sha256 hex of the 32 key bytes>"}``: registers the panel
  for the session (the first registration wins). Answer ``{active, since, session}``.
- ``draw``   stdin ``{"key": "<64 hex>"}``: the cards to draw, each question with its offer and
  buttons; records each offer the first time it is drawn. Answer ``{session, cards}``.
- ``press``  ``--offer <offer_id> --choice <n>``, stdin ``{"key": "<64 hex>"}``: one button.
  Answer: see ``plumb.mod.press``.

Exit codes: 0 done, 1 the card no longer exists, 2 usage (no such button), 3 refused (the agent
session marker, no panel registered, no key, another key, an offer never drawn): nothing
written."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from plumb.cliutil import EXIT_OK, EXIT_REFUSED, EXIT_USAGE, add_common, resolve_root


def _answer(data: Any, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")
    elif isinstance(data, dict) and data.get("line"):
        print(data["line"])


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="plumb mod")
    parser.add_argument("action", choices=("hello", "draw", "press"))
    add_common(parser)
    parser.add_argument("--session", required=True)
    parser.add_argument("--offer", default=None)
    parser.add_argument("--choice", type=int, default=None)
    args = parser.parse_args(argv)
    from plumb.api import open_core
    from plumb.mod import offers, press, session

    payload = session.read_stdin_json(sys.stdin)
    root = Path(resolve_root(args.root))
    try:
        if args.action == "hello":
            core = open_core(root)
            data = session.hello(core, args.session, payload.get("key_digest"))
            _answer({"active": bool(data["active"]), "since": data["since"],
                     "session": args.session}, args.as_json)
            return EXIT_OK
        if args.action == "draw":
            digest = session.check_key(root, args.session, payload, "draw")
            core = open_core(root)
            _answer({"session": args.session,
                     "cards": offers.drawn_cards(core, args.session, digest),
                     "settled": offers.settled_cards(core, args.session)}, args.as_json)
            return EXIT_OK
        if not args.offer or args.choice is None:
            print("plumb mod press: --offer and --choice are required", file=sys.stderr)
            return EXIT_USAGE
        core = open_core(root)
        _answer(press.press(core, args.session, args.offer, args.choice, payload),
                args.as_json)
        return EXIT_OK
    except session.Refused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    except press.Unknown as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
