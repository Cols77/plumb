"""``plumb quotes recover [IDs] [--dry-run] [--json]`` (SR-118): find older records' words in
past session transcripts and keep them for the record's card. It confirms nothing."""

from __future__ import annotations

import argparse
import json
import sys


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb quotes",
        description="Find older records' words in past session transcripts (shown on the "
                    "record's card as found, not verified; nothing is confirmed)")
    sub = parser.add_subparsers(dest="action", required=True)
    rec = sub.add_parser("recover", help="find the words of records whose quote is in no "
                                         "logged prompt (all such intents when no ID is given)")
    rec.add_argument("ids", nargs="*", help="record IDs (a requirement stands for its intents)")
    rec.add_argument("--dry-run", action="store_true",
                     help="ask no model and write nothing: list what would be examined")
    rec.add_argument("--json", action="store_true", help="print JSON")
    rec.add_argument("--root", default=None, help="repository root")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    from plumb.api import open_core
    from plumb.cliutil import resolve_root
    from plumb.understand import recover

    core = open_core(resolve_root(args.root))
    outcome = recover.recover(core, args.ids or None, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"findings": [f.to_dict() for f in outcome.findings],
                          "errors": [{"id": i, "error": e} for i, e in outcome.errors],
                          "skipped": outcome.skipped, "would_examine": outcome.planned},
                         ensure_ascii=False, indent=1))
    else:
        for line in outcome.skipped:
            print(f"plumb: skipped {line}")
        for plan in outcome.planned:
            exact = (f"; its quote is word for word in a message of {plan['at'][:10]}"
                     if plan["word_for_word"] else "")
            print(f"plumb: would examine {plan['id']} against {plan['candidates']} of your "
                  f"messages{exact}")
        for finding in outcome.findings:
            lines = recover.finding_lines(finding.to_dict())
            print(f"{finding.id}: {lines[0]}")
            for more in lines[1:]:
                print(f"  {more}")
        for rid, error in outcome.errors:
            print(f"plumb: {rid}: {error}; nothing decided", file=sys.stderr)
        if not (outcome.skipped or outcome.planned or outcome.findings or outcome.errors):
            print("plumb: no record awaits its words")
    return 1 if outcome.errors else 0
