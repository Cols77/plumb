"""Commands of sub-project 2 (sp2 5 to 9): ``capture``, ``new``, ``intent``, ``example``,
``decide``, ``escalate``, ``spec``, ``triage``, ``config``, ``jev`` and ``clarify``.

Owner-only writes (``spec approve``, ``triage --approve``, ``config auto-approve``, the owner's
``escalate decline``) go through ``approvals.require_owner`` only: refused under the session
marker and outside an interactive terminal (exit 3), on every host.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

from plumb.cliutil import EXIT_FINDINGS, EXIT_REFUSED, EXIT_USAGE, add_common, emit, resolve_root


def _parser(command: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"plumb {command}", description=description)
    add_common(parser)
    return parser


def _core(args: argparse.Namespace) -> Any:
    from plumb.api import open_core

    return open_core(resolve_root(args.root))


def _guarded(action: Callable[[], int | None]) -> int:
    """Map the capture and guard errors to exit codes: 2 usage, 3 refused, 1 findings."""
    from plumb.approvals import ApprovalError, Declined, Refused
    from plumb.capture.records import CaptureError

    try:
        return int(action() or 0)
    except Refused as exc:
        print(f"plumb: refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except CaptureError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ApprovalError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_FINDINGS
    except Declined as exc:
        print(f"{exc}")
        return 0


# --------------------------------------------------------------------------- capture


def cmd_capture(command: str, argv: list[str]) -> int:
    from plumb.capture.capture import capture, load_document, result_lines

    parser = _parser(command, "Record a whole read-back in one call: the owner's verbatim "
                     "words, the restatement, will, won't, assumptions, requirements with "
                     "given/when/then examples, decisions with alternatives; all proposed. "
                     "Prints the intent card for your reply.")
    parser.add_argument("--file", default="-", help="the JSON or YAML document (- = stdin)")
    parser.add_argument("--prompt", default=None,
                        help="the logged prompt's digest: the quote must be verbatim in it")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        import dataclasses

        from plumb.capture.records import CaptureError

        if args.file == "-":
            text = sys.stdin.read()
        else:
            try:
                with open(args.file, encoding="utf-8") as handle:
                    text = handle.read()
            except OSError as exc:
                raise CaptureError(f"cannot read {args.file}: {exc}") from exc
        result = capture(core, load_document(text), prompt_digest=args.prompt,
                         dry_run=args.dry_run)
        emit(dataclasses.asdict(result) if args.as_json else result_lines(result),
             args.as_json)
        return 0

    return _guarded(act)


# --------------------------------------------------------------------------- records


def cmd_new(command: str, argv: list[str]) -> int:
    from plumb.capture.records import KINDS, intent_fields, new_record

    parser = _parser(command, "Write one record with the next ID, proposed.")
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--title", required=True)
    parser.add_argument("--statement", default=None, help="requirement statement")
    parser.add_argument("--feature", default=None, help="requirement: its FEAT")
    parser.add_argument("--quote", default=None, help="intent: the owner's verbatim words")
    parser.add_argument("--readback", default=None, help="intent: the read-back")
    parser.add_argument("--description", default=None, help="feature description")
    parser.add_argument("--question", default=None, help="decision question")
    parser.add_argument("--chosen", default=None, help="decision: the chosen option")
    parser.add_argument("--derives-from", action="append", default=[], dest="derives")
    parser.add_argument("--body", default="")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        fields: dict[str, Any] = {"title": args.title}
        if args.kind == "intent":
            fields = intent_fields(args.quote or "", args.readback or "", title=args.title)
        for key in ("statement", "feature", "description", "question", "chosen"):
            value = getattr(args, key)
            if value is not None:
                fields[key] = value
        record = new_record(core, args.kind, fields, args.body, derives_from=args.derives)
        emit({"id": record.id, "path": record.path, "hash": record.hash} if args.as_json
             else f"plumb: {record.id} proposed ({record.path})", args.as_json)
        return 0

    return _guarded(act)


def cmd_intent(command: str, argv: list[str]) -> int:
    from plumb.capture.records import write_intent

    parser = _parser(command, "Record the owner's words and your read-back as an INT, "
                     "proposed.")
    parser.add_argument("--quote", required=True, help="the owner's verbatim words")
    parser.add_argument("--readback", required=True, help="your restatement")
    parser.add_argument("--will", action="append", default=[])
    parser.add_argument("--wont", action="append", default=[])
    parser.add_argument("--assume", action="append", default=[], dest="assumptions")
    parser.add_argument("--title", default="")
    parser.add_argument("--prompt", default=None, help="the logged prompt's digest")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        if args.prompt:
            from plumb.capture.capture import check_quote

            check_quote(core, args.prompt, args.quote)
        record = write_intent(core, args.quote, args.readback, will=args.will,
                              wont=args.wont, assumptions=args.assumptions, title=args.title,
                              prompt=args.prompt)
        emit({"id": record.id, "path": record.path} if args.as_json
             else f"plumb: {record.id} proposed ({record.path})", args.as_json)
        return 0

    return _guarded(act)


def cmd_example(command: str, argv: list[str]) -> int:
    from plumb.capture.records import add_example

    parser = _parser(command, "Append a given/when/then example EX-n to a requirement.")
    parser.add_argument("sr")
    parser.add_argument("--given", required=True)
    parser.add_argument("--when", required=True)
    parser.add_argument("--then", required=True)
    parser.add_argument("--quote", default=None,
                        help="the owner's verbatim words this example restates")
    parser.add_argument("--prompt", default=None, help="the logged prompt's digest")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        if args.prompt and args.quote:
            from plumb.capture.capture import check_quote

            check_quote(core, args.prompt, args.quote)
        was = core.status([args.sr]).get(args.sr)
        record, example_id = add_example(core, args.sr, args.given, args.when, args.then,
                                         args.quote)
        state = core.status([record.id])[record.id].confirmation
        lines = [f"plumb: {record.id} {example_id} added; {record.id} {state}"]
        if was is not None and was.confirmation == "confirmed":
            lines.append(f"plumb: {record.id} was confirmed; this edit needs the owner again")
        emit({"id": record.id, "example": example_id, "state": state} if args.as_json
             else lines, args.as_json)
        return 0

    return _guarded(act)


def cmd_decide(command: str, argv: list[str]) -> int:
    from plumb.capture.records import decide

    parser = _parser(command, "Record a decision: \"I assumed A; B also fits\".")
    parser.add_argument("--question", default="")
    parser.add_argument("--chosen", required=True)
    parser.add_argument("--alt", action="append", default=[], dest="alternatives")
    parser.add_argument("--matters", action="store_true",
                        help="the answer changes what gets built (may be asked, once)")
    parser.add_argument("--recommend", default=None, dest="recommended")
    parser.add_argument("--decides", action="append", default=[])
    parser.add_argument("--derives-from", action="append", default=[], dest="derives")
    parser.add_argument("--supersede", default=None, metavar="DEC")
    parser.add_argument("--rationale", default="")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        record = decide(core, args.question, args.chosen, args.alternatives,
                        matters=args.matters, recommended=args.recommended,
                        decides=args.decides, derives_from=args.derives,
                        supersede=args.supersede, rationale=args.rationale)
        alts = record.fields.get("alternatives") or []
        line = (f"plumb: {record.id} proposed: I assumed {record.fields['chosen']}"
                + (f"; {' / '.join(alts)} also fits" if alts else ""))
        if args.supersede:
            line += f" (supersedes {args.supersede})"
        emit({"id": record.id, "path": record.path} if args.as_json else line, args.as_json)
        return 0

    return _guarded(act)


# --------------------------------------------------------------------------- escalation


def cmd_escalate(command: str, argv: list[str]) -> int:
    from plumb.capture.escalation import TRIGGERS, decline, escalation
    from plumb.contracts import DiffStats

    parser = _parser(command, "Escalation to an up-front spec: check prints the suggestions "
                     "(one line each, never a question); decline records the owner's no "
                     "(relayed with --prompt and --quote, or in the owner's own terminal).")
    parser.add_argument("action", choices=["check", "decline"])
    parser.add_argument("request", nargs="?", default=None, help="check: the request text")
    parser.add_argument("--matched", action="append", default=[], help="record IDs")
    parser.add_argument("--intent", default=None)
    parser.add_argument("--lines", type=int, default=None, help="changed lines of the diff")
    parser.add_argument("--files", type=int, default=None, help="changed files of the diff")
    parser.add_argument("--path", action="append", default=[], help="changed paths")
    parser.add_argument("--trigger", action="append", default=[], choices=list(TRIGGERS))
    parser.add_argument("--prompt", default=None, help="decline: the owner's prompt digest")
    parser.add_argument("--quote", default=None, help="decline: the owner's exact words")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        if args.action == "decline":
            entry = decline(core, intent=args.intent, triggers=args.trigger,
                            prompt=args.prompt, quote=args.quote)
            print(f"plumb: escalation declined for {entry.payload.get('intent') or 'this work'}"
                  f" ({', '.join(entry.payload['triggers'])}; {entry.payload['by']}); not "
                  "suggested again")
            return 0
        diff = None
        if args.lines is not None or args.files is not None or args.path:
            diff = DiffStats(lines=args.lines or 0, files=args.files or len(args.path),
                             paths=tuple(args.path))
        found = escalation(core, prompt=args.request, matched=args.matched, diff=diff,
                           intent=args.intent)
        if args.as_json:
            import dataclasses

            emit([dataclasses.asdict(f) for f in found], True)
        else:
            emit([f.line for f in found] or ["plumb: no escalation suggested"], False)
        return 0

    return _guarded(act)


def cmd_spec(command: str, argv: list[str]) -> int:
    from plumb.capture.spec import SpecError, approve_set, set_state, show_lines

    parser = _parser(command, "An escalated spec (an INT with mode escalated and members): "
                     "show prints every member in full with the set hash; approve is the "
                     "owner's one set-hash approval, in the owner's own terminal only.")
    parser.add_argument("action", choices=["show", "approve", "state"])
    parser.add_argument("anchor", metavar="INT")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        try:
            if args.action == "show":
                lines = show_lines(core, args.anchor)
                emit({"lines": lines} if args.as_json else lines, args.as_json)
            elif args.action == "state":
                state = set_state(core, args.anchor)
                emit({"anchor": args.anchor, "state": state} if args.as_json
                     else f"{args.anchor}: {state}", args.as_json)
            else:
                entry = approve_set(core, args.anchor, note=args.note)  # asks y/N
                print(f"plumb: approved the escalated spec {args.anchor} "
                      f"({len(entry.payload['records'])} records, set "
                      f"{entry.payload['set']['hash'][:19]})")
        except SpecError as exc:
            print(f"plumb: {exc}", file=sys.stderr)
            return EXIT_FINDINGS
        return 0

    return _guarded(act)


# --------------------------------------------------------------------------- triage


def cmd_triage(command: str, argv: list[str]) -> int:
    from plumb.capture.triage import approve_low_risk, log_triage, triage, view_lines

    parser = _parser(command, "Proposed records grouped by faithfulness to your words (the "
                     "low-risk group first, riskier records individually). Advisory: it "
                     "approves nothing. --approve low-risk is your one step, in your own "
                     "terminal only.")
    parser.add_argument("--approve", choices=["low-risk"], default=None)
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        if args.approve:
            entry = approve_low_risk(core, note=args.note)  # asks y/N
            ids = [r["id"] for r in entry.payload["records"]]
            print(f"plumb: approved {', '.join(ids)} (low-risk group, by: owner)")
            left_out = entry.payload["triage"].get("left_out") or []
            if left_out:
                print("plumb: changed since the listing, left out: " + ", ".join(left_out))
            return 0
        view = triage(core)
        log_triage(core, view)
        if args.as_json:
            import dataclasses

            emit(dataclasses.asdict(view), True)
        else:
            emit(view_lines(view), False)
        return 0

    return _guarded(act)


HANDLERS: dict[str, Callable[[str, list[str]], int]] = {
    "triage": cmd_triage,
    "escalate": cmd_escalate,
    "spec": cmd_spec,
    "capture": cmd_capture,
    "new": cmd_new,
    "intent": cmd_intent,
    "example": cmd_example,
    "decide": cmd_decide,
}


def _utf8_stdout() -> None:
    """Cards carry glyphs (R9); a piped Windows stdout defaults to the locale code page."""
    encoding = str(getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if encoding != "utf8" and reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def run(command: str, argv: list[str]) -> int:
    _utf8_stdout()
    handler = HANDLERS.get(command)
    if handler is None:
        print(f"plumb: '{command}' is not available in this build", file=sys.stderr)
        return EXIT_USAGE
    try:
        return handler(command, argv)
    except SystemExit as exc:  # argparse usage errors and --help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
