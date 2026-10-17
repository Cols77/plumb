"""The intent loop's commands and state (SR-193, SR-194, SR-197; DEC-082).

``plumb intent open [--wait]`` collects the check of the owner's latest ``/plumb intent
<words>`` (``cmd_clarify.wait``) and opens the loop's state file; an ordinary message opens
none. ``plumb intent gate clarify|plan --intent INT-### --findings FILE`` records a stage's
judge gate: it passes only when no high or medium finding remains, and ``plan`` refuses while
``clarify`` has not passed. ``plumb intent done --intent INT-###`` refuses while the plan gate
has not passed or a requirement of the intent lacks proof evidence that passed. ``plumb intent
status`` lists the open loops.

State lives in ``.plumb/session/<id>/intent/<digest12>.json``. It carries no authority: it
confirms nothing, and the records stay proposed until the owner confirms them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root
from plumb.understand import files, gate

LOOP_VERBS = ("open", "gate", "done", "status", "adopt")
STAGES = ("clarify", "plan", "build")
LEVELS = ("high", "medium", "low")
BLOCKING = ("high", "medium")
GATE_OPEN_REASON = "the intent loop reached a clear intent"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def loop_path(root: Path, session: str, digest: str) -> Path:
    return files.session_dir(root, session) / "intent" / (
        digest.removeprefix("sha256:")[:12] + ".json")


def open_loop(root: Path, session: str, digest: str) -> Path:
    """Open the loop state of the commanded message ``digest`` (idempotent)."""
    path = loop_path(root, session, digest)
    if not path.exists():
        files.write_json_atomic(path, {
            "digest": digest, "intent": None, "opened_at": _now(),
            "stages": {stage: {"state": "open"} for stage in STAGES}})
    return path


def loops(root: Path, session: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    """Every loop state file (of one session, or all), newest opened last."""
    folder = Path(root) / ".plumb" / "session"
    found = []
    for path in sorted(folder.glob(f"{session or '*'}/intent/*.json")):
        data = files.read_json(path)
        if isinstance(data, Mapping) and isinstance(data.get("stages"), Mapping):
            found.append((path, dict(data)))
    return sorted(found, key=lambda item: str(item[1].get("opened_at", "")))


def _find(root: Path, session: str | None, intent: str) -> tuple[Path, dict[str, Any]]:
    """The loop of ``intent``, else this session's newest loop no intent claimed yet (it is
    claimed). With no session known nothing is claimed: another session's loop is not ours."""
    found = [(p, d) for p, d in loops(root, session) if not d.get("handed_to")]
    for path, data in reversed(found):
        if data.get("intent") == intent:
            return path, data
    for path, data in reversed(found if session else []):
        if data.get("intent") is None:
            data["intent"] = intent
            return path, data
    raise LookupError(f"no open loop for {intent}: plumb intent open comes first"
                      + ("" if session else " (or name the session with --session)"))


def _passed(data: Mapping[str, Any], stage: str) -> bool:
    return data["stages"].get(stage, {}).get("state") == "passed"


def _session(args: argparse.Namespace, root: Path) -> str | None:
    from plumb.stale import SESSION_ENV, current_session

    if args.session:
        return str(args.session)
    return current_session(root) if any(os.environ.get(n) for n in SESSION_ENV) else None


def _intent(core: Any, intent: str) -> None:
    record = core.index().get(intent)
    if record is None or record.kind != "intent":
        raise LookupError(f"no intent {intent}")


def requirements_of(core: Any, intent: str) -> list[str]:
    """The requirements linked to ``intent`` (derives_from or decides)."""
    return sorted(r.id for r in core.index().values() if r.kind == "requirement" and any(
        link.kind in ("derives_from", "decides") and link.target.record == intent
        for link in r.links))


def findings_from(path: str) -> list[dict[str, str]]:
    """The findings file: a JSON list of ``{level: high|medium|low, what}``."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"--findings {path}: {exc}") from exc
    if not isinstance(raw, list) or not all(isinstance(f, Mapping) for f in raw):
        raise ValueError(f"--findings {path}: a JSON list of {{level, what}}")
    out = []
    for finding in raw:
        level = str(finding.get("level") or "").lower()
        if level not in LEVELS:
            raise ValueError(f"--findings {path}: level is one of {', '.join(LEVELS)}")
        out.append({"level": level, "what": str(finding.get("what") or "")})
    return out


# --------------------------------------------------------------------------- verbs


def cmd_open(core: Any, args: argparse.Namespace) -> int:
    from plumb.understand import clarify, cmd_clarify

    root = Path(core.root)
    session = _session(args, root)
    outcome = cmd_clarify.wait(core, session, timeout=args.timeout, stream=sys.stderr)
    logged = cmd_clarify.latest_prompt(core, session)
    opened = None
    # SR-193 EX-4: an ordinary message opens no loop
    if logged is not None and logged.get("digest") == outcome.digest and outcome.digest \
            and clarify.commanded_words(str(logged.get("text") or "")) is not None:
        opened = open_loop(root, str(logged.get("session") or session or "default"),
                           outcome.digest)
    lines = [*outcome.lines, *(["plumb: intent loop open: " + opened.as_posix()] if opened else [])]
    emit({**outcome.as_json(), "loop": opened.as_posix() if opened else None, "lines": lines}
         if args.as_json else lines, args.as_json)
    return 0


def cmd_gate(core: Any, args: argparse.Namespace) -> int:
    root = Path(core.root)
    _intent(core, args.intent)
    path, data = _find(root, _session(args, root), args.intent)
    findings = findings_from(args.findings)
    data["files"] = sorted({*data.get("files", ()), str(Path(args.findings).resolve())})
    if args.stage == "plan" and not _passed(data, "clarify"):
        print("plumb: the clarify gate has not passed; plumb intent gate clarify comes first",
              file=sys.stderr)
        return EXIT_FINDINGS
    blocking = [f for f in findings if f["level"] in BLOCKING]
    if blocking:
        print(f"plumb: the {args.stage} gate does not pass: {len(blocking)} finding(s) above low "
              "remain; fix them and judge again", file=sys.stderr)
        for finding in blocking:
            print(f"  {finding['level']}: {finding['what']}", file=sys.stderr)
        return EXIT_FINDINGS
    data["stages"][args.stage] = {"state": "passed", "at": _now(), "findings": len(findings)}
    files.write_json_atomic(path, data)
    core.log_append("events", "intent-gate", {"intent": args.intent, "digest": data["digest"],
                                              "stage": args.stage, "findings": len(findings)})
    # SR-196: the loop opens only the hold of an intent change; a waiting card or a failed
    # check keeps the gate closed until the owner answers or releases it (SR-169 EX-3)
    if args.stage == "clarify" and gate.closed_reason(root, path.parent.parent.name).startswith(
            gate.INTENT_CHANGE):
        gate.open(core, path.parent.parent.name, data["digest"], "intent", GATE_OPEN_REASON)
    print(f"plumb: {args.intent}: the {args.stage} gate passed "
          f"({len(findings)} low finding(s) left)")
    return 0


def cmd_done(core: Any, args: argparse.Namespace) -> int:
    from plumb.capture import proof

    root = Path(core.root)
    _intent(core, args.intent)
    path, data = _find(root, _session(args, root), args.intent)
    missing = [] if _passed(data, "plan") else ["the plan gate has not passed"]
    required = requirements_of(core, args.intent)
    if not required:     # SR-197 EX-2: nothing captured is no proof shown
        missing.append(f"no requirement derives from {args.intent}: no proof to show")
    missing += [f"{row['id']} ({row['title']}): proof {row['why']}"
                for row in proof.not_shown(core, required)]
    if missing:
        print(f"plumb: {args.intent} is not done; the intent stays open:", file=sys.stderr)
        for line in missing:
            print(f"  {line}", file=sys.stderr)
        return EXIT_FINDINGS
    data["stages"]["build"] = {"state": "passed", "at": _now()}
    files.write_json_atomic(path, data)
    core.log_append("events", "intent-done", {"intent": args.intent, "digest": data["digest"]})
    _clean_up(root, path, data)
    print(f"plumb: {args.intent} done: every proof shown (the records stay as they are)")
    return 0


def _clean_up(root: Path, path: Path, data: Mapping[str, Any]) -> None:
    """SR-308: remove the ended loop's own working files: the findings and plan files its gates
    were given, its state file and, when no other loop of its session is open, the session's
    judge results and answered or withdrawn cards. Records and log entries stay."""
    import shutil

    from plumb.understand import cardstore

    session = path.parent.parent.name
    for name in data.get("files", ()):
        Path(name).unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    if any(not _passed(d, "build") and not d.get("handed_to") for _, d in loops(root, session)):
        return      # another loop of this session still needs them
    shutil.rmtree(files.results_dir(root, session), ignore_errors=True)
    cards = cardstore.own_cards(root, session)
    if cards:
        cardstore.save(root, session, [c for c in cards
                                       if c.status not in ("answered", "withdrawn")])


def cmd_status(core: Any, args: argparse.Namespace) -> int:
    root = Path(core.root)
    found = [(p, d) for p, d in loops(root, _session(args, root)) if not _passed(d, "build")
             and not d.get("handed_to")]
    if args.as_json:
        emit([d for _, d in found], True)
        return 0
    for _, data in found:
        states = ", ".join(f"{s} {data['stages'].get(s, {}).get('state', 'open')}" for s in STAGES)
        print(f"{data.get('intent') or data['digest'].removeprefix('sha256:')[:12]}: {states}")
    if not found:
        print("plumb: no intent loop is open")
    return 0


def _checkouts(root: Path) -> list[Path]:
    """This checkout, then the main checkout when this is a worktree (SR-302 EX-2)."""
    from plumb.awareness import gitfiles

    common = gitfiles.common_dir(root)
    main = common.parent if common is not None and common.name == ".git" else root
    return [root, main] if main.resolve() != root.resolve() else [root]


def cmd_adopt(core: Any, args: argparse.Namespace) -> int:
    """SR-302: take over an open loop of another session: copy it into this session, mark the
    old copy handed over and open the old session's gate."""
    from plumb.api import open_core

    root = Path(core.root)
    session = _session(args, root)
    if session is None:
        print("plumb: name the session that takes the loop over with --session", file=sys.stderr)
        return EXIT_USAGE
    found = [(r, p, d) for r in _checkouts(root) for p, d in loops(r)
             if not d.get("handed_to") and not _passed(d, "build")
             and (r != root or p.parent.parent.name != session)
             and (not args.from_session or p.parent.parent.name == args.from_session)
             and (not args.intent or d.get("intent") == args.intent)
             and (not args.digest or str(d["digest"]).removeprefix("sha256:").startswith(
                 args.digest.removeprefix("sha256:")))]
    if not found:
        print("plumb: no open loop matches; nothing taken over", file=sys.stderr)
        return EXIT_FINDINGS
    if len(found) > 1:  # never guess: the others may be loops other sessions still run
        print("plumb: more than one open loop matches; name one with --from-session, --intent "
              "or --digest; nothing taken over:", file=sys.stderr)
        for _r, p, d in found:
            print(f"  session {p.parent.parent.name}: {d.get('intent') or 'no intent yet'} "
                  f"({str(d['digest']).removeprefix('sha256:')[:12]})", file=sys.stderr)
        return EXIT_FINDINGS
    old_root, path, data = found[0]
    old_session = path.parent.parent.name
    mine = loop_path(root, session, data["digest"])
    files.write_json_atomic(mine, {**data, "adopted_from": {"root": old_root.as_posix(),
                                                           "session": old_session}})
    files.write_json_atomic(path, {**data, "handed_to": {"root": root.as_posix(),
                                                         "session": session, "at": _now()}})
    held = gate.state(old_root, old_session)
    if held.state == "closed":
        gate.open(open_core(old_root), old_session, held.message_digest, "handover",
                  f"the loop was taken over by session {session}")
    print(f"plumb: {data.get('intent') or 'the loop'} taken over from session {old_session}")
    return 0


def run(command: str, argv: list[str]) -> int:
    if not argv or argv[0] not in LOOP_VERBS:
        from plumb.capture import cli as capture_cli

        return int(capture_cli.run(command, argv) or 0)
    parser = argparse.ArgumentParser(
        prog="plumb intent",
        description="The intent loop: open it on the owner's /plumb intent <words>, record "
                    "each stage's judge gate, call it done once every proof is shown, or list "
                    "the open loops. Confirms nothing.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    opener = verbs.add_parser("open")
    opener.add_argument("--wait", action="store_true", help="(always waits)")
    opener.add_argument("--timeout", type=float, default=None)
    gater = verbs.add_parser("gate")
    gater.add_argument("stage", choices=("clarify", "plan"))
    gater.add_argument("--intent", required=True, metavar="INT-###")
    gater.add_argument("--findings", required=True, metavar="FILE",
                       help="JSON list of {level: high|medium|low, what}")
    doner = verbs.add_parser("done")
    doner.add_argument("--intent", required=True, metavar="INT-###")
    verbs.add_parser("status")
    adopter = verbs.add_parser("adopt")
    adopter.add_argument("--from-session", default=None)
    adopter.add_argument("--intent", default=None, metavar="INT-###")
    adopter.add_argument("--digest", default=None)
    for sub in (opener, gater, doner, verbs.choices["status"], adopter):
        add_common(sub)
        sub.add_argument("--session", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    from plumb.api import open_core

    core = open_core(resolve_root(args.root))
    try:
        return {"open": cmd_open, "gate": cmd_gate, "done": cmd_done, "status": cmd_status,
                "adopt": cmd_adopt}[
            args.verb](core, args)
    except (LookupError, ValueError) as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_FINDINGS if isinstance(exc, LookupError) else EXIT_USAGE
