"""The debug workflow (SR-220, SR-221, SR-300), standalone: ``plumb debug [ID ...] [--dry-run]``.

The cases plumb could not settle on its own (today: stale and dangling links) are rerun once
through the step the turn end runs, ``links.repin_after_tests`` (tests, then the meaning
cascade). What each case did and what it still needs is reported as text; a record whose
meaning changed under a decision becomes one owner question through the question tool (SR-300
EX-3), never a card. The plumb line counts the cases in debugging and the ones resolved.
Nothing here confirms anything or changes a record's meaning.
"""

from __future__ import annotations

import sys
from typing import Any

LINE = "plumb: debug: {n} cases, {resolved} resolved, {open} still in debugging"
DANGLING = "its target no longer exists, so there is nothing to repin to: relink it"


def cases(core: Any, selectors: list[str], *, dry_run: bool = False,
          session: str | None = None, **test_doubles: Any) -> list[dict[str, str]]:
    """One ``{case, state, what}`` per stale or dangling link of ``selectors`` (record IDs or
    link ids; none: every record with one). ``state`` is ``resolved``, ``would resolve`` (dry
    run) or ``open``; ``what`` says what happened or what is missing."""
    from plumb import stale
    from plumb.links import LinkError, repin_after_tests

    states = [s for s in core.link_states() if s.state in ("stale", "dangling")]
    records = selectors or sorted({s.link.source for s in states})
    where = session or stale.current_session(core.root)
    out: list[dict[str, str]] = []
    for record in records:
        wanted = record.split("#")[0]
        out += [{"case": s.link.id, "state": "open", "what": DANGLING} for s in states
                if s.state == "dangling" and s.link.source == wanted
                and (record == wanted or s.link.id == record)]
        try:
            step = repin_after_tests(core, record, session=where, dry_run=dry_run,
                                     **test_doubles)
        except LinkError as exc:
            out.append({"case": record, "state": "open", "what": str(exc)})
            continue
        out += [{"case": c["link"], "state": "resolved",
                 "what": f"repinned ({c.get('tier', 'tests pass')})"} for c in step.changes]
        out += [{"case": link, "state": "would resolve", "what": why} for link, why in step.would]
        out += [{"case": link, "state": "open", "what": why} for link, why in step.refused]
    return out


def run(command: str, argv: list[str]) -> int:
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Run the debug cases once (stale links through tests and the meaning "
                    "cascade) and say what each did and what it still needs. Never confirms.")
    add_common(parser)
    parser.add_argument("selector", nargs="*", help="record IDs or link ids; default: all")
    parser.add_argument("--dry-run", action="store_true",
                        help="ask the models only: no tests, no repin, no owner question")
    args = parser.parse_args(argv)
    found = cases(open_core(resolve_root(args.root)), args.selector, dry_run=args.dry_run)
    resolved = sum(c["state"] != "open" for c in found)
    if args.as_json:
        emit({"cases": found, "resolved": resolved}, True)
    else:
        print(LINE.format(n=len(found), resolved=resolved, open=len(found) - resolved))
        for c in found:
            print(f"  {c['case']}: {c['state']}: {c['what']}")
    return 1 if resolved < len(found) else 0


if __name__ == "__main__":
    sys.exit(run("debug", sys.argv[1:]))
