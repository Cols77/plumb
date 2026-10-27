"""``plumb inflight``: the intent other branches have in flight (ruling R17, SR-080, SR-081).

The agent's interface; the owner asks in plain words ("what are the other branches working
on?", "is anyone else changing the relay checks?") or ``/plumb status``.

- ``plumb inflight [--json]``: every active claim of ``refs/plumb/claims`` (branch, summary,
  records) and the conflicts raised on them;
- ``plumb inflight check <request words> [--json]``: the read-back check of plumb-clarify
  (the early conflict cards and warnings); it writes nothing;
- ``plumb inflight drop <branch or claim>``: the owner dropped that work, so its claim goes;
- ``plumb inflight sync``: carry this branch's changed records and the owner's answers to
  raised conflicts into the register (the stop hook does this on its own).

Exit codes: 0, 1 when ``check`` found a conflict, 2 usage.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from plumb.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root


def _parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plumb inflight", description=description)
    add_common(parser)
    return parser


def _core(args: argparse.Namespace) -> Any:
    from plumb.api import open_core

    return open_core(resolve_root(args.root))


def _list(argv: list[str]) -> int:
    from plumb.awareness import inflight
    from plumb.present import owner_text as text

    args = _parser("The intent other branches have in flight (refs/plumb/claims).") \
        .parse_args(argv)
    core = _core(args)
    me, claims = inflight.others(core, allow_git=True)
    if args.as_json:
        emit({"branch": me, "claims": claims}, True)
        return 0
    if not claims:
        emit([text.INFLIGHT_NONE], False)
        return 0
    lines = [text.INFLIGHT_HEADER]
    for claim in claims:
        records = sorted((claim.get("records") or {}).items())
        names = ", ".join(f'{i} "{e.get("title", "")}"' for i, e in records)
        lines.append(text.INFLIGHT_LINE.format(branch=claim.get("branch"),
                                               summary=claim.get("summary") or "",
                                               records=names))
        for conflict in claim.get("conflicts") or []:
            lines.append(f"    raised {conflict.get('dec')} with branch "
                         f"{conflict.get('branch')} on {conflict.get('record')}: "
                         f"{conflict.get('state')}"
                         + (f", chosen: {conflict['chosen']}" if conflict.get("chosen")
                            else ""))
    emit(lines, False)
    return 0


def _check(argv: list[str]) -> int:
    from plumb.awareness.early import check_text, notes

    parser = _parser("The early intent-conflict check of a request (writes nothing).")
    parser.add_argument("request", nargs="+")
    args = parser.parse_args(argv)
    result = check_text(_core(args), " ".join(args.request))
    lines = notes(result.conflicts) + result.lines
    if args.as_json:
        emit({"conflicts": [conflict.__dict__ for conflict in result.conflicts],
              "lines": lines}, True)
    else:
        emit(lines, False)
    return EXIT_FINDINGS if result.conflicts else 0


def _drop(argv: list[str]) -> int:
    from plumb.awareness import inflight

    parser = _parser("Drop the claims of a branch (or one claim): the owner dropped that work.")
    parser.add_argument("what")
    args = parser.parse_args(argv)
    removed = inflight.drop(_core(args), args.what)
    emit({"removed": removed} if args.as_json else
         [f"plumb: no longer in flight: {', '.join(removed) or 'nothing matched'}"],
         args.as_json)
    return 0


def _sync(argv: list[str]) -> int:
    from plumb.awareness import inflight
    from plumb.awareness.publish import publish
    from plumb.awareness.turn import claim_changes

    args = _parser("Carry this branch's changes and answers into the register.") \
        .parse_args(argv)
    core = _core(args)
    claimed = claim_changes(core, publish(core, []))
    synced = inflight.sync_decisions(core)
    emit({"claimed": claimed, "synced": synced}
         if args.as_json else
         [f"plumb: intent in flight {'updated' if claimed or synced else 'already current'}"],
         args.as_json)
    return 0


def run(command: str, argv: list[str]) -> int:
    del command
    actions = {"check": _check, "drop": _drop, "sync": _sync, "list": _list}
    if argv and argv[0] in actions:
        action, rest = actions[argv[0]], argv[1:]
    elif argv and not argv[0].startswith("-"):
        print(f"plumb inflight: unknown action {argv[0]!r} (check, drop, sync, list)",
              file=sys.stderr)
        return EXIT_USAGE
    else:
        action, rest = _list, argv
    try:
        return action(rest)
    except Exception as exc:  # noqa: BLE001 - one line, never a traceback
        from plumb.awareness.inflight import InflightBusy

        if isinstance(exc, InflightBusy):
            print(f"plumb inflight: {exc}", file=sys.stderr)
            return EXIT_USAGE
        raise
