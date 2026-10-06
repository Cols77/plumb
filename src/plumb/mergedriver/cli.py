"""``plumb merge-driver``, ``plumb conflicts``, ``plumb conflict propose|choose|relay``.

The agent's interface (sp6 8.4, 11). The owner says "keep feat-x's version" or uses
``/plumb conflicts``; the agent runs these. ``conflict choose`` without ``--prompt`` is the
owner's own terminal (exit 3 elsewhere, nothing written); with ``--prompt`` and ``--quote``
(or as ``conflict relay``) it relays the owner's logged words, checked like an approval.
"""

from __future__ import annotations

import sys
from typing import Any


def _values(path: str | None) -> Any:
    if not path:
        return None
    from pathlib import Path

    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _conflicts(argv: list[str]) -> int:
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, emit, resolve_root
    from plumb.mergedriver import conflicts as mod
    from plumb.present import owner_text

    parser = argparse.ArgumentParser(
        prog="plumb conflicts",
        description="The intent conflicts a merge left in record files, as cards: both "
                    "versions, what merged on its own, an advisory compatibility judgment. "
                    "Nothing is chosen.")
    parser.add_argument("words", nargs="*", help="a conflict, a record or plain words")
    add_common(parser)
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    found = list(mod.open_conflicts(core))
    if args.words:
        found = [mod.find(core, " ".join(args.words))] if found else []
    _request_cards(core, [c.ic for c in found])
    if args.as_json:
        emit({"conflicts": [{**mod.stated_key(c), "title": c.title, "labels": list(c.labels),
                             "fields": dict(c.fields), "merged": list(c.merged),
                             "proposed": c.proposed, "card": mod.conflict_card(core, c)}
                            for c in found]}, True)
        return 0
    if not found:
        print(owner_text.NO_CONFLICTS)
        return 0
    for conflict in found:
        for line in mod.conflict_card(core, conflict):
            print(line)
    return 0


def _request_cards(core: Any, ics: list[str]) -> None:
    """Ask the stop hook to show these cards to the owner at the end of the turn (the
    agent's own output never reaches the stated set)."""
    if not ics:
        return
    import json
    import os

    from plumb.normalize import utc_now

    path = core.paths.session / "conflicts-requested.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"at": utc_now(), "ics": ics}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _conflict(argv: list[str]) -> int:
    import argparse

    from plumb.api import open_core
    from plumb.approvals import Declined, Refused
    from plumb.cliutil import add_common, emit, resolve_root
    from plumb.mergedriver import conflicts as mod
    from plumb.present import owner_text

    parser = argparse.ArgumentParser(
        prog="plumb conflict",
        description="propose: store a combined version (shown in the card; applies nothing). "
                    "choose: the owner's terminal, or with --prompt and --quote the owner's "
                    "relayed words. relay: choose with --prompt and --quote.")
    parser.add_argument("action", choices=["propose", "choose", "relay"])
    parser.add_argument("ref", nargs="+", help="an IC, a record or plain words")
    parser.add_argument("--take", default=None,
                        help="ours | theirs | combined, or a side's name (main, feat-x)")
    parser.add_argument("--file", default=None,
                        help="a YAML mapping of the conflicting fields (propose, combined)")
    parser.add_argument("--prompt", default=None, help="digest of the owner's logged prompt")
    parser.add_argument("--quote", default=None, help="the owner's exact words")
    add_common(parser)
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    ref = " ".join(args.ref)
    try:
        if args.action == "propose":
            conflict = mod.propose(core, ref, _values(args.file))
            print(owner_text.PROPOSED.format(record=conflict.record, title=conflict.title))
            for line in mod.conflict_card(core, conflict):
                print(line)
            _request_cards(core, [conflict.ic])
            return 0
        if not args.take:
            print("plumb: --take is required (ours, theirs, combined or a side's name)",
                  file=sys.stderr)
            return 2
        relayed = args.action == "relay" or args.prompt is not None
        if relayed:
            if not args.prompt or not args.quote:
                print("plumb: a relayed choice needs --prompt and --quote", file=sys.stderr)
                return 2
            conflict, payload = mod.relay_choice(core, ref, args.take, prompt=args.prompt,
                                                 quote=args.quote,
                                                 values=_values(args.file))
        else:
            try:
                conflict, payload = mod.choose_owner(core, ref, args.take,
                                                     values=_values(args.file))
            except Refused:
                theirs = mod.find(core, ref).labels[1]
                print(owner_text.CHOOSE_REFUSED.format(theirs=theirs), file=sys.stderr)
                return 3
    except mod.ChoiceRefused as exc:
        print(f"plumb: choice refused: {exc}", file=sys.stderr)
        return 3
    except Declined:
        print("plumb: nothing chosen", file=sys.stderr)
        return 1
    except mod.ConflictError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    line = mod.chosen_line(core, conflict, payload["take"], payload)
    if args.as_json:
        emit({**payload, "line": line}, True)
    else:
        print(line)
    return 0


def run(command: str, argv: list[str]) -> int:
    if command == "merge-driver":
        from plumb.mergedriver.driver import main

        return main(argv)
    if command == "conflicts":
        return _conflicts(argv)
    return _conflict(argv)
