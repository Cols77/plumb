"""Commands of sub-project 2 (sp2 5 to 9): ``capture``, ``new``, ``intent``, ``example``,
``decide``, ``escalate``, ``spec``, ``config``, ``jev`` and ``clarify``.

Owner-only writes (``config auto-approve``, the owner's ``escalate decline``) go through
``approvals.require_owner`` only: refused under the session marker and outside an interactive
terminal (exit 3), on every host. ``spec approve`` and ``triage`` no longer exist (SR-210, SR-380).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

from iaso.cliutil import EXIT_FINDINGS, EXIT_REFUSED, EXIT_USAGE, add_common, emit, resolve_root


def _parser(command: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"iaso {command}", description=description)
    add_common(parser)
    return parser


def _core(args: argparse.Namespace) -> Any:
    from iaso.api import open_core

    return open_core(resolve_root(args.root))


def _guarded(action: Callable[[], int | None]) -> int:
    """Map the capture and guard errors to exit codes: 2 usage, 3 refused, 1 findings."""
    from iaso.approvals import ApprovalError, Declined, Refused
    from iaso.capture.records import CaptureError

    try:
        return int(action() or 0)
    except Refused as exc:
        print(f"iaso: refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except CaptureError as exc:
        print(f"iaso: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ApprovalError as exc:
        print(f"iaso: {exc}", file=sys.stderr)
        return EXIT_FINDINGS
    except Declined as exc:
        print(f"{exc}")
        return 0


# --------------------------------------------------------------------------- capture


def cmd_capture(command: str, argv: list[str]) -> int:
    from iaso.capture.capture import capture, load_document, result_lines

    parser = _parser(command, "Record a whole read-back in one call: the owner's verbatim "
                     "words, the restatement, will, won't, assumptions, requirements with "
                     "given/when/then examples, decisions with alternatives; all proposed. "
                     "Prints what it wrote, for you.")
    parser.add_argument("--file", default="-", help="the JSON or YAML document (- = stdin)")
    parser.add_argument("--prompt", default=None,
                        help="the logged prompt's digest: the quote must be verbatim in it")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        import dataclasses

        from iaso.capture.records import CaptureError

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
    from iaso.capture.records import KINDS, intent_fields, new_record

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
        lines = [f"iaso: {record.id} proposed ({record.path})"]
        if args.kind == "intent":  # no --prompt here: the quote is never checked
            from iaso.capture.capture import UNCHECKED_NOTE

            lines.append("iaso: " + UNCHECKED_NOTE.replace("give --prompt", "use iaso "
                                                            "intent --prompt"))
        emit({"id": record.id, "path": record.path, "hash": record.hash} if args.as_json
             else lines, args.as_json)
        return 0

    return _guarded(act)


def cmd_intent(command: str, argv: list[str]) -> int:
    from iaso.capture.records import write_intent

    parser = _parser(command, "Record the owner's words and your read-back as an INT, "
                     "proposed.")
    parser.add_argument("--quote", required=True, help="the owner's verbatim words")
    parser.add_argument("--readback", required=True, help="your restatement")
    parser.add_argument("--will", action="append", default=[])
    parser.add_argument("--wont", action="append", default=[])
    parser.add_argument("--assume", action="append", default=[], dest="assumptions")
    parser.add_argument("--title", default="")
    parser.add_argument("--prompt", default=None, help="the logged prompt's digest")
    parser.add_argument("--question", default=None,
                        help="the question the quote answered (for a short answer)")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        from iaso.capture.capture import UNCHECKED_NOTE, check_quote
        from iaso.capture.records import ANSWER_NEEDS_QUESTION, is_short_answer

        prompt = (str(check_quote(core, args.prompt, args.quote)["digest"]) if args.prompt
                  else None)
        record = write_intent(core, args.quote, args.readback, will=args.will,
                              wont=args.wont, assumptions=args.assumptions, title=args.title,
                              prompt=prompt, question=args.question)
        lines = [f"iaso: {record.id} proposed ({record.path})"]
        if prompt is None:
            lines.append("iaso: " + UNCHECKED_NOTE)
        if is_short_answer(args.quote) and not (args.question or "").strip():
            lines.append("iaso: " + ANSWER_NEEDS_QUESTION)
        emit({"id": record.id, "path": record.path, "quote_checked": prompt is not None}
             if args.as_json else lines, args.as_json)
        return 0

    return _guarded(act)


def cmd_example(command: str, argv: list[str]) -> int:
    from iaso.capture.records import add_example

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
        from iaso.capture.capture import UNCHECKED_NOTE, check_quote

        prompt = None
        if args.prompt and args.quote:
            prompt = str(check_quote(core, args.prompt, args.quote)["digest"])
        was = core.status([args.sr]).get(args.sr)
        record, example_id = add_example(core, args.sr, args.given, args.when, args.then,
                                         args.quote, prompt)
        state = core.status([record.id])[record.id].confirmation
        lines = [f"iaso: {record.id} {example_id} added; {record.id} {state}"]
        if args.quote and prompt is None:
            lines.append("iaso: " + UNCHECKED_NOTE)
        if was is not None and was.confirmation == "confirmed":
            lines.append(f"iaso: {record.id} was confirmed; this edit needs the owner again")
        emit({"id": record.id, "example": example_id, "state": state} if args.as_json
             else lines, args.as_json)
        return 0

    return _guarded(act)


def cmd_decide(command: str, argv: list[str]) -> int:
    from iaso.capture.records import decide

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
        line = (f"iaso: {record.id} proposed: I assumed {record.fields['chosen']}"
                + (f"; {' / '.join(alts)} also fits" if alts else ""))
        if args.supersede:
            line += f" (supersedes {args.supersede})"
        emit({"id": record.id, "path": record.path} if args.as_json else line, args.as_json)
        return 0

    return _guarded(act)


# --------------------------------------------------------------------------- escalation


def cmd_escalate(command: str, argv: list[str]) -> int:
    from iaso.capture.escalation import TRIGGERS, decline, escalation
    from iaso.contracts import DiffStats

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
            print(f"iaso: escalation declined for {entry.payload.get('intent') or 'this work'}"
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
            emit([f.line for f in found] or ["iaso: no escalation suggested"], False)
        return 0

    return _guarded(act)


def cmd_spec(command: str, argv: list[str]) -> int:
    from iaso.capture.spec import SpecError, set_state, show_lines

    parser = _parser(command, "An escalated spec (an INT with mode escalated and members): "
                     "show prints every member in full with the set hash; state says whether "
                     "the judge approved the set whole.")
    parser.add_argument("action", choices=["show", "state"])
    parser.add_argument("anchor", metavar="INT")
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
        except SpecError as exc:
            print(f"iaso: {exc}", file=sys.stderr)
            return EXIT_FINDINGS
        return 0

    return _guarded(act)


# --------------------------------------------------------------------------- clarify


def cmd_clarify(command: str, argv: list[str]) -> int:
    from iaso.capture.clarify import clarify, view_lines, write_session

    parser = _parser(command, "The clarification depth of a request (trivial, incremental, "
                     "escalated), what confirmed records already answer, and which drafted "
                     "questions matter, ranked: ask the first, one per message.")
    parser.add_argument("request", nargs="+")
    parser.add_argument("--questions", default=None,
                        help="JSON list of {question, options, recommended}")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        import dataclasses
        import json

        from iaso.capture.records import CaptureError

        questions = []
        if args.questions:
            try:
                with open(args.questions, encoding="utf-8") as handle:
                    questions = json.load(handle)
            except (OSError, ValueError) as exc:
                raise CaptureError(f"cannot read {args.questions}: {exc}") from exc
            if not isinstance(questions, list) or not all(isinstance(q, dict)
                                                          for q in questions):
                raise CaptureError("--questions takes a JSON list of objects")
        request = " ".join(args.request)
        view = clarify(core, request, questions)
        write_session(core, view, request)
        emit(dataclasses.asdict(view) if args.as_json else view_lines(view), args.as_json)
        return 0

    return _guarded(act)


# --------------------------------------------------------------------------- jev, config


def cmd_jev(command: str, argv: list[str]) -> int:
    from iaso.capture import jevcmd
    from iaso.capture.calibrate import CalibrationUnavailable, calibrate, result_lines

    parser = _parser(command, "The optional JEV backend: status (never the secret), setup "
                     "(records only the credential variable's NAME), calibrate (measures it "
                     "on your own decisions before any auto-approval).")
    parser.add_argument("action", choices=["status", "setup", "calibrate"])
    parser.add_argument("--probe", action="store_true", help="status: one call, 2 s limit")
    parser.add_argument("--provider", default=None, choices=["typesafe", "openrouter"],
                        help="setup: the provider preset (endpoint, model, variable name)")
    parser.add_argument("--env-var", default=None,
                        help="setup: the variable that holds the credential (default: the "
                        "provider's, TYPESAFE_API_KEY or OPENROUTER_API_KEY)")
    parser.add_argument("--env-file", default=None,
                        help="setup: an env file OUTSIDE the repository the key is read from "
                        "in place (recorded in ~/.config/iaso/jev.json, never copied)")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        if args.action == "status":
            data = jevcmd.jev_status(core, probe=args.probe)
            emit(data if args.as_json else jevcmd.status_lines(data), args.as_json)
            return 0
        if args.action == "setup":
            emit(jevcmd.jev_setup(core, env_var=args.env_var, base_url=args.base_url,
                                  provider=args.provider, env_file=args.env_file), False)
            return 0
        try:
            entry, results = calibrate(core)
        except CalibrationUnavailable as exc:
            emit({"calibrated": False, "reason": str(exc)} if args.as_json
                 else f"calibration: {exc}", args.as_json)
            return EXIT_FINDINGS
        if args.as_json:
            emit(dict(entry.payload), True)
        else:
            emit(result_lines(entry.payload["per_kind"], entry.payload.get("model_version")),
                 False)
        return 0 if any(r.passing for r in results.values()) else EXIT_FINDINGS

    return _guarded(act)


def cmd_config(command: str, argv: list[str]) -> int:
    from iaso.capture import jevcmd

    parser = _parser(command, "Owner settings: auto-approve on|off and show run in your own "
                     "terminal only (logged in the event log); card is retired.")
    parser.add_argument("setting", choices=["auto-approve", "show", "card"])
    parser.add_argument("value", nargs="?", default=None)
    parser.add_argument("--backend", default="jev")
    parser.add_argument("--min-probability", type=float, default=0.9)
    parser.add_argument("--min-confidence", default="high", choices=["low", "medium", "high"])
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> int:
        if args.setting == "show":
            emit(jevcmd.config_show(core), False)
            return 0
        if args.setting == "card":
            from iaso.config import CARD_RETIRED

            print(CARD_RETIRED)  # SR-173: the setting is retired and changes nothing
            return 0
        if args.value not in ("on", "off"):
            parser.error("auto-approve takes on or off")
        try:
            jevcmd.auto_approve(core, args.value == "on", backend=args.backend,
                                min_probability=args.min_probability,
                                min_confidence=args.min_confidence)
        except jevcmd.ConfigRefused as exc:
            print(f"iaso: auto-approve stays off: {exc}", file=sys.stderr)
            return EXIT_FINDINGS
        print(f"iaso: auto-approve {args.value} (by: owner; logged)")
        return 0

    return _guarded(act)


HANDLERS: dict[str, Callable[[str, list[str]], int]] = {
    "jev": cmd_jev,
    "config": cmd_config,
    "clarify": cmd_clarify,
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
        print(f"iaso: '{command}' is not available in this build", file=sys.stderr)
        return EXIT_USAGE
    try:
        return handler(command, argv)
    except SystemExit as exc:  # argparse usage errors and --help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
