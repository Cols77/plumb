"""``plumb merge-driver``, ``plumb conflicts``, ``plumb conflict propose|choose|relay``.

The agent's interface (sp6 8.4, 11). The owner says "keep feat-x's version" or uses
``/plumb conflicts``; the agent runs these. ``conflict choose`` is the owner's own terminal
(exit 3 elsewhere, nothing written). The agent never carries the owner's answer (DEC-057):
``conflict relay`` and ``choose --prompt/--quote`` are refused; the owner answers on the card
or in chat, where the prompt hook reads it (``understand.read``).
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
    settled = _apply_settled(core)
    found = list(mod.open_conflicts(core))
    early = _early_open(core, " ".join(args.words))
    if args.words and found:
        try:
            found = [mod.find(core, " ".join(args.words))]
        except mod.ConflictError as exc:
            if not early:
                print(str(exc), file=sys.stderr)
                return 1
            found = []
    _request_cards(core, [c.ic for c in found])
    if args.as_json:
        emit({"conflicts": [{**mod.stated_key(c), "title": c.title, "labels": list(c.labels),
                             "fields": dict(c.fields), "merged": list(c.merged),
                             "proposed": c.proposed, "card": mod.conflict_card(core, c)}
                            for c in found],
              "early": [{"dec": dec, "record": record, "card": card}
                        for dec, record, card in early],
              "settled": settled}, True)
        return 0
    for line in settled:
        print(line)
    if not found and not early:
        if not settled:
            print(owner_text.NO_CONFLICTS)
        return 0
    for conflict in found:
        for line in mod.conflict_card(core, conflict):
            print(line)
    for _dec, _record, card in early:
        for line in card:
            print(line)
    return 0


def _apply_settled(core: Any) -> list[str]:
    """R17: a merge-time conflict the owner already answered before work began is settled
    by that answer, never asked again (``answer.apply_settled``)."""
    try:
        from plumb.awareness.answer import apply_settled

        return apply_settled(core)
    except Exception:  # noqa: BLE001 - the card still asks
        return []


def _early_open(core: Any, words: str) -> list[tuple[str, str, list[str]]]:
    """``[(DEC, record, card)]``: the early intent conflicts still waiting for the owner's
    answer (R17), as the card capture showed, and asked of the stop hook so the owner sees
    them at the end of the turn. A decision whose record a merge left in conflict is asked
    by that merge card alone (one card per record; its answer answers the decision)."""
    try:
        from plumb.awareness import early as early_mod
        from plumb.awareness.answer import card_conflict, early_decisions, waiting_on_conflict
    except ImportError:
        return []
    index = core.index()
    pending = [e for e in early_decisions(index)
               if e.record in index and not waiting_on_conflict(index, e.dec)
               and core.status([e.dec])[e.dec].confirmation != "confirmed"]
    if words.strip():
        wanted = words.strip().upper()
        pending = [e for e in pending if wanted in (e.dec, e.record)
                   or set(words.lower().split()) & set(index[e.record].title.lower().split())]
    out: list[tuple[str, str, list[str]]] = []
    requested = []
    for e in pending:
        conflict = card_conflict(core, e)
        out.append((e.dec, e.record, early_mod.card(conflict)))
        requested.append(conflict)
    early_mod.request_cards(core, requested)
    return out


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
        description="propose: store a combined version (--file) and/or suggest a side (--take "
                    "with --why); shown on the card, applies nothing. choose: the owner's "
                    "terminal. relay, and choose with --prompt or --quote, are refused.")
    parser.add_argument("action", choices=["propose", "choose", "relay"])
    parser.add_argument("ref", nargs="+", help="an IC, a record or plain words")
    parser.add_argument("--take", default=None,
                        help="ours | theirs | combined, or a side's name (main, feat-x)")
    parser.add_argument("--file", default=None,
                        help="a YAML mapping of the conflicting fields (propose, combined)")
    parser.add_argument("--why", default="",
                        help="propose --take: the one-line reason for the suggested side")
    parser.add_argument("--prompt", default=None, help="digest of the owner's logged prompt")
    parser.add_argument("--quote", default=None, help="the owner's exact words")
    add_common(parser)
    args = parser.parse_args(argv)
    if args.action == "relay" or args.prompt is not None or args.quote is not None:
        print("plumb: nothing was chosen. The owner answers on the conflict's card or in chat, "
              "and plumb reads it; the agent does not relay it", file=sys.stderr)
        return 3
    core = open_core(resolve_root(args.root))
    ref = " ".join(args.ref)
    if args.action != "propose":
        try:
            from plumb.awareness.answer import merge_conflict_of
        except ImportError:
            merge_conflict_of = None  # noqa: N806
        ic = merge_conflict_of(core, ref) if merge_conflict_of is not None else None
        if ic:
            ref = ic  # the merge card asks this question; its answer answers the decision
        elif _is_early(core, ref, mod):
            return _early_answer(core, args, ref)
    try:
        if args.action == "propose":
            if args.take and not args.why.strip():
                print("plumb: a suggestion needs its reason (--why)", file=sys.stderr)
                return 2
            conflict = mod.propose(core, ref, _values(args.file), take=args.take, why=args.why)
            print((owner_text.PROPOSED if conflict.proposed else owner_text.SUGGESTED).format(
                record=conflict.record, title=conflict.title))
            for line in mod.conflict_card(core, conflict):
                print(line)
            _request_cards(core, [conflict.ic])
            return 0
        if not args.take:
            print("plumb: --take is required (ours, theirs, combined or a side's name)",
                  file=sys.stderr)
            return 2
        try:
            conflict, payload = mod.choose_owner(core, ref, args.take,
                                                 values=_values(args.file))
        except Refused:
            theirs = mod.find(core, ref).labels[1]
            print(owner_text.CHOOSE_REFUSED.format(theirs=theirs), file=sys.stderr)
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


def _is_early(core: Any, ref: str, mod: Any) -> bool:
    """The reference names an early intent conflict (a DEC capture raised, R17), or no
    merge-time conflict is open and plain words may name one."""
    try:
        from plumb.awareness.answer import early_decisions, is_early_ref, shown_cards
    except ImportError:
        return False
    if is_early_ref(core, ref):
        return True
    if mod.open_conflicts(core):
        return False
    return bool(early_decisions(core.index())) or bool(shown_cards(core, ref))


def _early_answer(core: Any, args: Any, ref: str) -> int:
    """The owner's answer to an early conflict card: their own terminal (``choose``)."""
    from plumb.approvals import Declined, Refused
    from plumb.awareness import answer
    from plumb.cliutil import emit

    try:
        if not args.take:
            print("plumb: --take is required (a branch's name, or both)", file=sys.stderr)
            return 2
        try:
            early, payload = answer.choose_owner(core, ref, args.take)
        except Refused:
            from plumb.present import owner_text

            print(owner_text.CHOOSE_REFUSED.format(theirs=answer.find(core, ref).other),
                  file=sys.stderr)
            return 3
    except answer.AnswerRefused as exc:
        print(f"plumb: answer refused: {exc}", file=sys.stderr)
        return 3
    except Declined:
        print("plumb: nothing chosen", file=sys.stderr)
        return 1
    except answer.AnswerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    line = answer.answer_line(core, early, str(payload["choice"]["take"]))
    if args.as_json:
        emit({"dec": early.dec, "record": early.record, **payload, "line": line}, True)
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
