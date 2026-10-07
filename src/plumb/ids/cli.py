"""``plumb ids [sync] [--json]`` and ``plumb merge-fix [--dry-run] [--json] [--from REF]``
(sp6 4.3, 5; SR-070, SR-071).

``merge-fix`` changes no intent (it renumbers mechanically), so the agent runs it without
the owner's words; its text output is in the owner's terms (titles, never paths) and names
no shell command (``present.owner_text``). Exit codes: 0 nothing left to fix, 1 a collision
remains, 2 usage.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from typing import Any


def _parser(prog: str, description: str) -> argparse.ArgumentParser:
    from plumb.cliutil import add_common

    parser = argparse.ArgumentParser(prog=prog, description=description)
    add_common(parser)
    return parser


def _core(args: argparse.Namespace) -> Any:
    from plumb.api import open_core
    from plumb.cliutil import resolve_root

    return open_core(resolve_root(args.root))


def _state_lines(state: Any) -> list[str]:
    if not state.reserved:
        return ["plumb ids: not reserved (no git repository); the highest local numbers: "
                + (", ".join(f"{p} {n}" for p, n in sorted(state.high.items())) or "none")]
    lines = ["plumb ids: refs/plumb/ids, shared by every worktree of this clone"]
    lines.append("highest reserved: " + (", ".join(f"{p} {n}" for p, n in
                                                     sorted(state.high.items())) or "none"))
    for item in list(state.recent)[-5:]:
        lines.append(f"  {item.get('id')} on {item.get('branch')} at {item.get('at')}")
    return lines


def cmd_ids(argv: list[str]) -> int:
    from plumb import ids
    from plumb.cliutil import emit

    parser = _parser("plumb ids", "The IDs reserved in refs/plumb/ids; `sync` rescans every "
                     "local branch and raises the reserved numbers over them.")
    parser.add_argument("action", nargs="?", choices=("status", "sync"), default="status")
    args = parser.parse_args(argv)
    core = _core(args)
    state = ids.sync(core.paths) if args.action == "sync" else ids.state(core.paths)
    data = asdict(state)
    emit(data if args.as_json else _state_lines(state), args.as_json)
    return 0


def cmd_merge_fix(argv: list[str]) -> int:
    from plumb import ids
    from plumb.cliutil import emit

    parser = _parser("plumb merge-fix", "Renumber an ID a merge brought twice: the branch "
                     "merged into keeps its IDs; the incoming record gets a newly reserved "
                     "ID and every reference the incoming side added follows it. Stages the "
                     "result during a merge; never commits, never rewrites history.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; write and "
                        "reserve nothing")
    parser.add_argument("--from", dest="from_ref", default=None, metavar="REF",
                        help="preview the collisions merging REF would bring (read only)")
    args = parser.parse_args(argv)
    core = _core(args)
    result = ids.merge_fix(core, dry_run=args.dry_run or bool(args.from_ref),
                           from_ref=args.from_ref)
    if args.as_json:
        emit(asdict(result), True)
    else:
        emit(list(result.lines), False)
    return 1 if result.remaining else 0


def run(command: str, argv: list[str]) -> int:
    try:
        if command == "merge-fix":
            return cmd_merge_fix(argv)
        return cmd_ids(argv)
    except SystemExit as exc:  # argparse --help or usage error
        return int(exc.code or 0) if isinstance(exc.code, int) else 2
    except Exception as exc:  # an error with its own exit code (IdBusy)
        code = getattr(exc, "exit_code", None)
        if not isinstance(code, int):
            raise
        print(str(exc), file=sys.stderr)
        return code
