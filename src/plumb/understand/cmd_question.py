"""``plumb question reword`` (SR-362, DEC-340): what the coding agent may do with the judge's
questions before the owner sees them.

``reword --covers KEY[,KEY...] --question Q --header H --options JSON`` records the agent's
wording of the judge questions it covers, in the owner's terms and merged on one principle
(``judge.reword``): the owner's answer to it answers each of them. A KEY is a judge question's
text as ``clarify --wait`` gives it, or a start of it naming one open question. Nothing here
drops, answers or defaults a question: one the owner already answered is the judge's to not
raise (``judge._questions``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any

NO_MATCH = "plumb: {key!r} names no open question of the judge; nothing recorded."
REWORDED = "plumb: your wording covers {n} question(s); the owner's answer to it answers each."


def _resolve(keys: Sequence[str], words: str) -> str | None:
    """The open question key ``words`` names: its text, or a start of it naming only one."""
    from plumb.understand.judge import question_key

    want = question_key(words)
    if want in keys:
        return want
    found = [k for k in keys if want and k.startswith(want)]
    return found[0] if len(found) == 1 else None


def _covered(keys: Sequence[str], given: Sequence[str]) -> list[str] | str:
    """The keys each ``--covers`` value names, whole or split on commas; else the value that
    names none."""
    out: list[str] = []
    for value in given:
        whole = _resolve(keys, value)
        parts = [whole] if whole else [_resolve(keys, p) for p in value.split(",")]
        if None in parts:
            return value
        out += [p for p in parts if p and p not in out]
    return out


def _options(raw: str) -> list[dict[str, Any]] | None:
    """The question tool's options: two to four ``{label, description}``."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, list) or not 2 <= len(data) <= 4 or not all(
            isinstance(o, Mapping) and str(o.get("label") or "").strip() for o in data):
        return None
    return [{"label": str(o["label"]), "description": str(o.get("description") or "")}
            for o in data]


def run(command: str, argv: list[str]) -> int:
    from plumb.api import open_core
    from plumb.cliutil import add_common, resolve_root
    from plumb.stale import current_session
    from plumb.understand import judge

    parser = argparse.ArgumentParser(prog="plumb question")
    add_common(parser)
    parser.add_argument("--session", default="")
    sub = parser.add_subparsers(dest="verb", required=True)
    reword = sub.add_parser("reword", help="your wording of the judge questions it covers")
    reword.add_argument("--covers", action="append", required=True)
    reword.add_argument("--question", required=True)
    reword.add_argument("--header", required=True)
    reword.add_argument("--options", required=True, help="JSON: [{label, description}, ...]")
    args = parser.parse_args(argv)
    root = resolve_root(args.root)
    core = open_core(root)
    session = args.session or current_session(root)
    keys = [str(q.get("key")) for q in judge.open_questions(core, session)]
    covers = _covered(keys, args.covers)
    options = _options(args.options)
    if isinstance(covers, str):
        print(NO_MATCH.format(key=covers), file=sys.stderr)
        return 1
    if options is None:
        print("plumb: --options is a JSON list of two to four {label, description}.",
              file=sys.stderr)
        return 2
    if judge._LEFT_IN.search(" ".join([args.question, args.header,
                                       *(o["label"] for o in options)])):
        print("plumb: put the question in the owner's terms, with no record id.",
              file=sys.stderr)        # SR-362 EX-1
        return 2
    judge.reword(core, session, covers, args.question, args.header, options)
    print(REWORDED.format(n=len(covers)))
    return 0
