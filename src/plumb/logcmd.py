"""``plumb log migrate [--dry-run] [--check] [--json]`` (SP6 6.5, SR-074).

The agent runs it when the owner says "migrate the logs" (or /plumb migrate the logs): every
line of the legacy ``events.jsonl`` and ``evidence.jsonl`` becomes its own entry file with
exactly the line's fields, so every digest, ``prev`` link and evidence identity is unchanged.
It changes no intent and approves nothing. Exit codes: 0 done (or nothing left), 1 refused
(a bad line, named) or, with ``--check``, legacy lines remain; 2 usage.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from plumb.cliutil import add_common, emit, resolve_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plumb log",
        description="Move the legacy JSONL log lines into one file per entry, keeping every "
                    "digest and the hash chain.")
    sub = parser.add_subparsers(dest="action")
    migrate = sub.add_parser("migrate", help="move legacy lines into entry files")
    add_common(migrate)
    migrate.add_argument("--dry-run", action="store_true", help="write nothing; list what "
                         "would be written")
    migrate.add_argument("--check", action="store_true", help="write nothing; exit 1 while "
                         "legacy lines remain")
    return parser


def run(command: str, argv: list[str]) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.action != "migrate":
        parser.print_usage(sys.stderr)
        return 2
    from plumb import log
    from plumb.paths import PlumbPaths

    paths = PlumbPaths(resolve_root(args.root))
    if args.check:
        remaining = log.legacy_count(paths)
        emit({"remaining": remaining} if args.as_json else
             f"plumb log: {remaining} legacy log lines remain" if remaining else
             "plumb log: no legacy log line remains", args.as_json)
        return 1 if remaining else 0
    report = log.migrate(paths, dry_run=args.dry_run)
    if args.as_json:
        emit(asdict(report), True)
    else:
        lines: list[str] = []
        if report.refused:
            lines.append("plumb log: refused; nothing was migrated (tamper evidence is never "
                         "carried into the new format):")
            lines.extend(f"  {problem}" for problem in report.refused)
        else:
            verb = "would write" if report.dry_run else "wrote"
            lines.append(f"plumb log: {report.lines} legacy lines; {verb} "
                         f"{len(report.written)} entry files, {report.skipped} already there")
            if report.truncated:
                lines.append("plumb log: emptied " + ", ".join(report.truncated)
                             + " (kept, so older branches still merge)")
        emit(lines, False)
    return 1 if report.refused else 0
