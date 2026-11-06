"""``plumb mod hello|room|study|known|loops``: the commands only plumb's panel (the Claude Code mod)
runs.

All of them take ``--session <id>`` and read one JSON object on stdin; none takes a key in argv.

- ``hello``  stdin ``{"key_digest": "<sha256 hex of the 32 key bytes>"}``: registers the panel
  for the session (the first registration wins). Answer ``{active, since, session}``.
- ``room``   ``--study <slug>``, stdin ``{"key": "<64 hex>"}``: the owner pressed the band's new
  study line: the browser room opens on it and the study is marked opened (SR-294). Answer
  ``{origin, slug, status}``.
- ``study``  ``--study <slug> --depth md|diagrams|none``, stdin ``{"key": "<64 hex>"}``: the
  owner's choice on a study idea in the band: accepted at that depth, or declined ('not now',
  ``none``) (SR-294 EX-7..EX-9, DEC-207). ``video`` is refused until video studies exist.
  Answer ``{slug, status, depth}``. Never opens the room. ``--refresh yes|no`` in place of
  ``--depth``: the owner's press on a study whose records changed: rewrite it at the same
  depth, or not now (SR-360 EX-2, DEC-336). Answer ``{slug, status, depth, refresh}``.
- ``known``  stdin ``{}``: the known problems the band counts and its pane lists (SR-367), read
  only. Answer ``{open, issues: [{id, title, symptom, cause, fix, fixed, state, history}]}``.
- ``loops``  stdin ``{}``: the loops of the project the band counts and its pane lists (SR-393),
  read only: what ``plumb loops --json`` answers, with the one change stamp's path.

Exit codes: 0 done, 1 no such study or it did not start, 2 usage, 3 refused (the agent
session marker, no panel registered, no key, another key): nothing written."""

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
    parser.add_argument("action", choices=("hello", "room", "study", "known", "loops"))
    add_common(parser)
    parser.add_argument("--session", required=True)
    parser.add_argument("--study", default=None)
    parser.add_argument("--depth", default=None)
    parser.add_argument("--refresh", choices=("yes", "no"), default=None)
    args = parser.parse_args(argv)
    from plumb.api import open_core
    from plumb.mod import session

    payload = session.read_stdin_json(sys.stdin)
    root = Path(resolve_root(args.root))
    try:
        if args.action == "hello":
            core = open_core(root)
            data = session.hello(core, args.session, payload.get("key_digest"))
            _answer({"active": bool(data["active"]), "since": data["since"],
                     "session": args.session}, args.as_json)
            return EXIT_OK
        if args.action == "known":
            from plumb import debug

            _answer(debug.known_pane(root), args.as_json)
            return EXIT_OK
        if args.action == "loops":
            from plumb.understand import loops

            _answer(loops.listing(root), args.as_json)
            return EXIT_OK
        if args.action == "room":
            from plumb.browser import launch

            session.check_key(root, args.session, payload, "room")
            if not args.study:
                print("plumb mod room: --study is required", file=sys.stderr)
                return EXIT_USAGE
            key = str(payload["key"]).lower()
            _answer(launch.open_study(root, args.session, key, args.study), args.as_json)
            return EXIT_OK
        if args.action == "study":
            from plumb import study

            session.check_key(root, args.session, payload, "study")
            if not args.study or not (args.depth or args.refresh):
                print("plumb mod study: --study and --depth (or --refresh) are required",
                      file=sys.stderr)
                return EXIT_USAGE
            try:
                if args.refresh:
                    chosen = study.refresh(root, args.study, args.refresh == "yes")
                    _answer({"slug": args.study, "status": chosen["status"],
                             "depth": chosen.get("depth", ""), "refresh": chosen["refresh"]},
                            args.as_json)
                    return EXIT_OK
                chosen = study.choose(root, args.study,
                                      None if args.depth == "none" else args.depth)
            except ValueError as exc:
                print(f"plumb mod study: {exc}", file=sys.stderr)
                return EXIT_USAGE
            _answer({"slug": args.study, "status": chosen["status"],
                     "depth": chosen.get("depth", "")}, args.as_json)
            return EXIT_OK
    except session.Refused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    except (LookupError, OSError) as exc:      # room: no such study, or it did not start
        print(f"plumb mod {args.action}: {exc}", file=sys.stderr)
        return 1
