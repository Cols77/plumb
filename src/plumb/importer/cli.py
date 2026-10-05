"""``plumb import pi-agent-factory <source> [--dry-run] [--only SR,FEAT,NC] [--json]``."""

from __future__ import annotations

import argparse
import sys

from plumb.cliutil import EXIT_USAGE, add_common, emit, resolve_root

TOOLS = ("pi-agent-factory",)


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb import", description="Import another tool's records as proposed plumb "
        "records. The source is read only; nothing is confirmed.")
    add_common(parser)
    parser.add_argument("tool", help="the source tool: pi-agent-factory")
    parser.add_argument("source", help="path of the source checkout")
    parser.add_argument("--dry-run", action="store_true", help="write nothing; report only")
    parser.add_argument("--only", default=None, help="comma-separated kinds: SR,FEAT,NC")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    if args.tool not in TOOLS:
        print(f"plumb import: unknown source tool {args.tool!r} (known: {', '.join(TOOLS)})",
              file=sys.stderr)
        return EXIT_USAGE
    from plumb.api import open_core
    from plumb.importer.pi_factory import import_pi_factory

    only = [k for k in args.only.split(",") if k.strip()] if args.only else None
    try:
        report = import_pi_factory(open_core(resolve_root(args.root)), args.source,
                                   dry_run=args.dry_run, only=only)
    except FileNotFoundError as exc:
        print(f"plumb import: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.as_json:
        emit(report, True)
        return 0
    verb = "would import" if args.dry_run else "imported"
    counts = ", ".join(f"{n} {kind}" for kind, n in report["counts"].items())
    lines = [f"plumb import: {verb} {counts or 'nothing'} from {report['source']} "
             f"(HEAD {(report['head'] or 'unknown')[:12]}); every record is proposed, "
             "nothing is confirmed"]
    for finding in report["findings"]:
        lines.append(f"{finding['kind']}: {finding['id']}: {finding['detail']}")
    lines.append(f"{len(report['findings'])} finding(s)")
    emit(lines, False)
    return 0
