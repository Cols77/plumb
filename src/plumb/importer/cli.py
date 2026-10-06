"""``plumb import pi-agent-factory <source> [--dry-run] [--diff] [--only SR,FEAT,NC,CLAIMS]
[--json] [--root <target>]`` (next-plan 9.1)."""

from __future__ import annotations

import argparse
import sys

from plumb.cliutil import EXIT_USAGE, add_common, emit, resolve_root

TOOLS = ("pi-agent-factory",)


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plumb import", description="Import another tool's records into plumb. The "
        "source is read only. Records arrive proposed, except a requirement whose upstream "
        "human consent pins its current content (by: import), once the owner confirms that "
        "in their own terminal. Re-running updates in place.")
    add_common(parser)
    parser.add_argument("tool", help="the source tool: pi-agent-factory")
    parser.add_argument("source", help="path of the source checkout")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan as a diff and write nothing")
    parser.add_argument("--diff", action="store_true", help="print the plan, then apply it")
    parser.add_argument("--only", default=None,
                        help="comma-separated kinds: SR,FEAT,NC,CLAIMS")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    if args.tool not in TOOLS:
        print(f"plumb import: unknown source tool {args.tool!r} (known: {', '.join(TOOLS)})",
              file=sys.stderr)
        return EXIT_USAGE
    from plumb.api import open_core
    from plumb.importer.pi_factory import ImportRefused, import_pi_factory

    only = [k for k in args.only.split(",") if k.strip()] if args.only else None
    try:
        report = import_pi_factory(open_core(resolve_root(args.root)), args.source,
                                   dry_run=args.dry_run, only=only, diff=args.diff)
    except (FileNotFoundError, ImportRefused) as exc:
        print(f"plumb import: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.as_json:
        emit(report, True)
        return 0
    lines: list[str] = []
    if args.dry_run or args.diff:
        lines.extend(report.get("diff") or [])
    verb = "would import" if args.dry_run else "imported"
    actions = report["actions"]
    approved = report.get("approved") or []
    lines.append(
        f"plumb import: {verb} from {report['source']} (HEAD "
        f"{(report['head'] or 'unknown')[:12]}): {actions['create']} created, "
        f"{actions['update']} updated, {actions['unchanged']} unchanged, {actions['skip']} "
        f"skipped; {len(approved)} confirmed by import (upstream consent on the current "
        "content), every other record proposed")
    for finding in report["findings"]:
        lines.append(f"{finding['kind']}: {finding['id']}: {finding['detail']}")
    counts = ", ".join(f"{n} {kind}" for kind, n in report["finding_counts"].items())
    lines.append(f"{len(report['findings'])} finding(s)" + (f": {counts}" if counts else ""))
    emit(lines, False)
    return 0
