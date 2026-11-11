"""PRESENT commands (sp5 5 to 8): the owner's commands take plain words.

``status`` (``--card``), ``brief``, ``drift``, ``show``, ``explain`` (alias ``why``),
``impact``, ``resolve``, ``review``, ``align`` and ``view``. Every argument that
names something may be plain words ("the login thing"), a path or an ID; IDs and paths still
work but are never required (R9). When the words do not clearly name one thing, the command
lists the candidates in the owner's terms and asks which one, instead of guessing.

The owner types these as ``/iaso <verb> <words>``; the agent runs them with the raw CLI and
answers in the owner's terms. None of them approves anything.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from typing import Any

from iaso.cliutil import EXIT_USAGE, add_common, emit, resolve_root

_ID = re.compile(r"^(?:(?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})$")


def _parser(command: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"iaso {command}", description=description)
    add_common(parser)
    return parser


def _core(args: argparse.Namespace) -> Any:
    from iaso.api import open_core

    return open_core(resolve_root(args.root))


def _delegate(command: str, argv: list[str]) -> int:
    """The unchanged sp1 handlers (``iaso.commands``) for brief, drift and plain status."""
    from iaso import commands

    return commands.run(command, argv)


def _resolve_or_ask(core: Any, words: list[str], as_json: bool,
                    kind: str | None = None) -> tuple[list[str], list[str], bool]:
    """``(record ids, paths, answered)``: ``answered`` is True when the candidates (or
    "nothing matches") were printed instead, as the answer to the owner's request."""
    from iaso.present.resolve import as_dict, resolution_lines, resolve

    if words and all(_ID.match(w) for w in words):
        return list(words), [], False
    resolution = resolve(core, " ".join(words), kind=kind)
    if resolution.ambiguous or resolution.how == "none":
        emit(as_dict(resolution) if as_json else resolution_lines(resolution), as_json)
        return [], [], True
    ids = [i.ref for i in resolution.items if i.kind == "record"]
    paths = [i.ref for i in resolution.items if i.kind in ("path", "test")]
    return ids, paths, False


# --------------------------------------------------------------------------- commands


def cmd_status(command: str, argv: list[str]) -> int:
    if "--card" not in argv:
        return _delegate(command, argv)
    parser = _parser(command, "The status line, what awaits you and drift, in a few lines.")
    parser.add_argument("--card", action="store_true")
    args = parser.parse_args(argv)
    from iaso.present.report import status_card_lines

    data = status_card_lines(_core(args))
    emit(data if args.as_json else data["lines"], args.as_json)
    return 0


def cmd_brief(command: str, argv: list[str]) -> int:
    """The sp1 brief, plus at most one line: the triage offer (R8 A). The lines come from
    ``iaso.present.api.brief``, which the MCP server and the adapters call as well."""
    from iaso.present import api

    parser = _parser(command, "The short intent brief (about 30 lines, cap 40).")
    parser.add_argument("--max-lines", type=int, default=None)
    parser.add_argument("--all", action="store_true", dest="show_all")
    args = parser.parse_args(argv)
    lines = api.brief(_core(args), full=args.show_all, max_lines=args.max_lines)
    emit({"lines": lines} if args.as_json else lines, args.as_json)
    return 0


def cmd_show(command: str, argv: list[str]) -> int:
    from iaso.readback import show_lines

    parser = _parser(command, "Print records in full: the read-back, will/won't, labelled "
                     "assumptions, every example, the alternatives and the body. Takes IDs or "
                     "plain words.")
    parser.add_argument("words", nargs="+", metavar="ID_OR_WORDS")
    args = parser.parse_args(argv)
    core = _core(args)
    # sp6 8.1: an IC-### is the intent conflict record on its record file
    from iaso.mergedriver.conflicts import conflict_cards, is_conflict_id

    conflict_ids = [w for w in args.words if is_conflict_id(w)]
    words = [w for w in args.words if not is_conflict_id(w)]
    conflict_lines, missing_ics = conflict_cards(core, conflict_ids)
    if not words:
        for ic in missing_ics:
            print(f"iaso: no open conflict {ic}", file=sys.stderr)
        emit({"lines": conflict_lines, "missing": missing_ics} if args.as_json
             else conflict_lines, args.as_json)
        return 1 if missing_ics else 0
    ids, _, answered = _resolve_or_ask(core, words, args.as_json)
    if answered:
        return 0
    lines, missing = show_lines(core, ids)
    lines = conflict_lines + lines + conflict_cards(core, ids, by_record=True)[0]
    missing = missing_ics + list(missing)
    for record_id in missing:
        print(f"iaso: no record {record_id}", file=sys.stderr)
    emit({"lines": lines, "missing": missing} if args.as_json else lines, args.as_json)
    return 1 if missing else 0


def cmd_explain(command: str, argv: list[str]) -> int:
    from iaso.explain import explain_lines

    parser = _parser(command, "Why a behaviour, a file or a record exists, in plain terms: "
                     "the requirement, the owner's words it comes from, decisions, examples, "
                     "test state and code. Takes plain words, a path or a record ID.")
    parser.add_argument("query", nargs="+", help="plain words, a file path or a record ID")
    args = parser.parse_args(argv)
    lines, data = explain_lines(_core(args), " ".join(args.query))
    emit({**data, "lines": lines} if args.as_json else lines, args.as_json)
    return 0 if data["records"] or data.get("candidates") else 1


def cmd_impact(command: str, argv: list[str]) -> int:
    parser = _parser(command, "What a change would reach: records and covering tests with "
                     "their evidence state. Takes plain words, a path or a record ID.")
    parser.add_argument("words", nargs="+", metavar="WORDS")
    args = parser.parse_args(argv)
    core = _core(args)
    exact = args.words[0].replace("\\", "/") if len(args.words) == 1 else ""
    if exact and (core.root / exact.split("::", 1)[0]).is_file():
        # a repository path or test node is its own answer: what a change to it reaches,
        # not the impact of the records that own it (VS4, SR-016)
        ids, paths = [], [exact]
    else:
        ids, paths, answered = _resolve_or_ask(core, args.words, args.as_json)
        if answered:
            return 0
    try:
        from iaso.verify.cli import run as verify_run
    except ImportError:
        print("iaso: impact is not available in this build", file=sys.stderr)
        return EXIT_USAGE
    common = ["--root", str(core.root)] + (["--json"] if args.as_json else [])
    code = 0
    for ref in [*ids, *paths][:3]:
        code = max(code, int(verify_run("impact", [ref, *common]) or 0))
    return code


def cmd_resolve(command: str, argv: list[str]) -> int:
    from iaso.present.resolve import as_dict, resolution_lines, resolve

    parser = _parser(command, "Map plain words to records, paths and tests, best first, "
                     "with the reason; asks which one when the match is unclear.")
    parser.add_argument("words", nargs="+")
    parser.add_argument("--kind", default=None, help="SR, INT, DEC, FEAT or NC")
    args = parser.parse_args(argv)
    resolution = resolve(_core(args), " ".join(args.words), kind=args.kind)
    emit(as_dict(resolution) if args.as_json else resolution_lines(resolution), args.as_json)
    return 1 if resolution.how == "none" else 0


def cmd_review(command: str, argv: list[str]) -> int:
    parser = _parser(command, "The deep review: what awaits you (triage groups, escalated "
                     "sets, decisions), approvals you did not type, drift and hints, edge "
                     "alignment and the merge state. Optional plain words scope it.")
    parser.add_argument("words", nargs="*")
    args = parser.parse_args(argv)
    from iaso.present.review import review

    core = _core(args)
    ids: list[str] = []
    if args.words:
        ids, _, answered = _resolve_or_ask(core, args.words, args.as_json)
        if answered:
            return 0
    data = review(core, ids or None)
    emit(data if args.as_json else data["lines"], args.as_json)
    return 0


def cmd_align(command: str, argv: list[str]) -> int:
    parser = _parser(command, "Judge each edge of a scope (intent, feature, requirement, "
                     "example, test, code, evidence), weakest first, and name the gaps. "
                     "Judgments never create or remove an edge.")
    parser.add_argument("words", nargs="*")
    args = parser.parse_args(argv)
    from iaso.align import align, align_lines

    core = _core(args)
    ids: list[str] | None = None
    if args.words:
        ids, _, answered = _resolve_or_ask(core, args.words, args.as_json)
        if answered:
            return 0
    from iaso.heavy import heavy

    with heavy(core.root, "iaso align"):
        result = align(core, ids)
    emit(result.as_dict() if args.as_json else align_lines(result), args.as_json)
    return 0


def cmd_context(command: str, argv: list[str]) -> int:
    """SR-374 EX-8: the full picture of one condition of the insight table, unfiltered."""
    from iaso.present import insights

    parser = _parser(command, "The full picture iaso has for one condition: session, "
                     "prompt <words>, edit <path>, test <node>, symptom <words>, "
                     "merge [<base>].")
    parser.add_argument("condition", choices=sorted(set(insights.TABLE) - {"cut"}))
    parser.add_argument("arg", nargs="*", metavar="PATH_OR_ID")
    args = parser.parse_args(argv)
    core = _core(args)
    arg = " ".join(args.arg)
    ctx: dict[str, Any] = {"full": True, "text": arg, "path": arg, "node": arg}
    if args.condition == "edit":
        from iaso import stale

        stale.ensure_linkmap(core)
    if args.condition == "test":
        from iaso.verify import open_verify

        ctx["regression"] = bool(open_verify(core).evidence([arg])[arg].regression)
    if args.condition == "merge":
        from iaso.boundary import merge_report
        from iaso.boundary.cli import merge_settings

        ctx["report"] = merge_report(core, arg or str(merge_settings(core)["default_base"]),
                                     run_full=False)
    lines = [line.text for line in insights.lines(args.condition, core, ctx)]
    emit({"lines": lines} if args.as_json else lines or ["iaso: nothing applies"],
         args.as_json)
    return 0


HANDLERS: dict[str, Callable[[str, list[str]], int]] = {
    "context": cmd_context,
    "status": cmd_status, "brief": cmd_brief, "drift": _delegate, "show": cmd_show,
    "explain": cmd_explain, "why": cmd_explain, "impact": cmd_impact,
    "resolve": cmd_resolve, "review": cmd_review,
    "align": cmd_align,
}


def run(command: str, argv: list[str]) -> int:
    handler = HANDLERS.get(command)
    if handler is None:
        print(f"iaso: '{command}' is not available in this build", file=sys.stderr)
        return EXIT_USAGE
    try:
        return handler(command, argv)
    except SystemExit as exc:  # argparse usage errors and --help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
