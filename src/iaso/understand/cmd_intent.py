"""The intent loop's commands and state (SR-193, SR-194, SR-197; DEC-082).

``iaso intent open [--wait]`` collects the check of the owner's latest ``/iaso intent
<words>`` (``cmd_clarify.wait``) and opens the loop's state file; an ordinary message opens
none. ``iaso intent gate clarify|plan --intent INT-### --findings FILE`` records a stage's
judge gate: it passes only when no high or medium finding remains, and ``plan`` refuses while
``clarify`` has not passed; a refused gate leaves ``stopped`` (what the loop waits for) in the
state. ``iaso intent progress --task <words> [--done N --total M] [--left <words>]...`` sets the
current step's task the band's bar draws (SR-291) and the tasks left its pane names (SR-305). ``iaso intent done --intent INT-###`` refuses while the plan gate
has not passed or a requirement of the intent lacks proof evidence that passed. ``iaso intent
status`` lists the open loops.

State lives in ``.iaso/session/<id>/intent/<digest12>.json``, with ``step`` (clarify, plan,
build, proven) derived from its stages and ``tasks`` ``{label, done, total|null, started_at}``.
The words ``intent progress`` sets do not outlive the loop's real state: a passing gate clears
them, and in the build step evidence recorded for one of the intent's requirements (``iaso
proof --evidence``, ``on_evidence``) or a refused ``intent done`` redraws the task as the proofs
shown over the proofs required, naming those not shown (report-d7f2612b).
It carries no authority: it confirms nothing, and the records stay proposed until the owner
confirms them.
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

from iaso.cliutil import EXIT_FINDINGS, EXIT_USAGE, add_common, emit, resolve_root
from iaso.understand import files, gate

LOOP_VERBS = ("open", "gate", "done", "status", "progress", "adopt")
STAGES = ("clarify", "plan", "build")
LEVELS = ("high", "medium", "low")
BLOCKING = ("high", "medium")
GATE_OPEN_REASON = "the intent loop reached a clear intent"
PROOFS_TASK = "proofs shown"     # the build step's task as the loop's real state draws it


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def loop_path(root: Path, session: str, digest: str) -> Path:
    return files.session_dir(root, session) / "intent" / (
        digest.removeprefix("sha256:")[:12] + ".json")


def save(path: Path, data: dict[str, Any]) -> None:
    """Write the loop state with its ``step``: the first stage not passed, ``proven`` after all."""
    data["step"] = next((s for s in STAGES if not _passed(data, s)), "proven")
    files.write_json_atomic(path, data)
    if len(path.parents) > 4:       # <root>/.iaso/session/<id>/intent/<file>
        from iaso.understand import loops

        loops.touch(path.parents[4])


def _stop(path: Path, data: dict[str, Any], what: str) -> None:
    """SR-291 EX-6: the loop's current step waits for ``what`` until the next pass."""
    data["stopped"] = what
    save(path, data)


def reset_head(root: Path, session: str) -> None:
    """SR-291: a loop that opens or is done leaves the band's head clean: the session's
    remembered intent, its summary in status.json and the last job's progress go (the next
    turn's end names the intent again)."""
    from iaso.present.cards import INTENT_FILE

    for stale in (files.session_dir(root, session) / INTENT_FILE,
                  files.progress_path(root, session)):
        stale.unlink(missing_ok=True)
    status_path = Path(root) / ".iaso" / "session" / "status.json"
    status = files.read_json(status_path)
    if isinstance(status, dict) and status.get("intent_summary"):
        files.write_json_atomic(status_path, {**status, "intent_summary": ""})


def open_loop(root: Path, session: str, digest: str, at: str = "") -> Path:
    """Open the loop state of the commanded message ``digest`` sent at ``at`` (idempotent); the
    same words retyped after the loop opened open a fresh loop (SR-222)."""
    path = loop_path(root, session, digest)
    held = files.read_json(path)
    if not isinstance(held, Mapping) or at > str(held.get("opened_at") or ""):
        reset_head(root, session)
        save(path, {
            "digest": digest, "intent": None, "opened_at": _now(),
            "stages": {stage: {"state": "open"} for stage in STAGES}, "tasks": None,
            "stopped": None})
    return path


def loops(root: Path, session: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    """Every loop state file (of one session, or all), newest opened last."""
    folder = Path(root) / ".iaso" / "session"
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
    raise LookupError(f"no open loop for {intent}: iaso intent open comes first"
                      + ("" if session else " (or name the session with --session)"))


def _passed(data: Mapping[str, Any], stage: str) -> bool:
    return data["stages"].get(stage, {}).get("state") == "passed"


def _session(args: argparse.Namespace, root: Path) -> str | None:
    from iaso.stale import SESSION_ENV, current_session

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


def _draw_proofs(core: Any, data: dict[str, Any]) -> bool:
    """report-d7f2612b: the build step's task from the loop's real state, not the words last
    set with ``intent progress``: the proofs shown over the proofs the intent requires, the
    requirements not shown left (the pane names them). Nothing outside the build step: the
    clarify and plan steps' tasks are their own words. Returns whether it drew."""
    from iaso.capture import proof

    if data.get("step") != "build" or not data.get("intent"):
        return False
    held = data.get("tasks") if isinstance(data.get("tasks"), Mapping) else {}
    required = requirements_of(core, data["intent"])
    missing = proof.not_shown(core, required)
    data["tasks"] = {
        "label": PROOFS_TASK, "done": len(required) - len(missing), "total": len(required) or None,
        "started_at": held.get("started_at") if held.get("label") == PROOFS_TASK else _now(),
        "left": [f"{row['id']} ({row['title']}): proof {row['why']}" for row in missing]}
    return True


def on_evidence(core: Any, sr_id: str) -> None:
    """Evidence recorded for the requirement ``sr_id`` moves every open loop (any session of
    this checkout) whose intent it serves: the band's task line follows the loop's real state
    (report-d7f2612b)."""
    root = Path(core.root)
    for path, data in loops(root):
        if data.get("handed_to") or _passed(data, "build") or not data.get("intent"):
            continue
        if sr_id in requirements_of(core, data["intent"]) and _draw_proofs(core, data):
            save(path, data)


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
    from iaso.understand import clarify, cmd_clarify

    root = Path(core.root)
    session = _session(args, root)
    outcome = cmd_clarify.wait(core, session, timeout=args.timeout, stream=sys.stderr)
    logged = cmd_clarify.latest_prompt(core, session)
    opened = None
    # SR-193 EX-4: an ordinary message opens no loop
    if logged is not None and logged.get("digest") == outcome.digest and outcome.digest \
            and clarify.commanded_words(str(logged.get("text") or "")) is not None:
        opened = open_loop(root, str(logged.get("session") or session or "default"),
                           outcome.digest, str(logged.get("at") or ""))
    lines = [*outcome.lines, *(["iaso: intent loop open: " + opened.as_posix()] if opened else [])]
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
        _stop(path, data, "the clarify gate")
        print("iaso: the clarify gate has not passed; iaso intent gate clarify comes first",
              file=sys.stderr)
        return EXIT_FINDINGS
    blocking = [f for f in findings if f["level"] in BLOCKING]
    if blocking:
        _stop(path, data, f"the {args.stage} gate: {len(blocking)} finding(s) to fix")
        print(f"iaso: the {args.stage} gate does not pass: {len(blocking)} finding(s) above low "
              "remain; fix them and judge again", file=sys.stderr)
        for finding in blocking:
            print(f"  {finding['level']}: {finding['what']}", file=sys.stderr)
        return EXIT_FINDINGS
    # SR-305: the pane names the low findings left
    data["stages"][args.stage] = {"state": "passed", "at": _now(), "findings": len(findings),
                                  "left": [f["what"] for f in findings]}
    data.update(tasks=None, stopped=None)   # the next step starts with no task drawn
    save(path, data)
    core.log_append("events", "intent-gate", {"intent": args.intent, "digest": data["digest"],
                                              "stage": args.stage, "findings": len(findings)})
    # SR-196: the loop opens only the hold of an intent change; a waiting card or a failed
    # check keeps the gate closed until the owner answers or releases it (SR-169 EX-3)
    if args.stage == "clarify" and gate.closed_reason(root, path.parent.parent.name).startswith(
            gate.INTENT_CHANGE):
        gate.open(core, path.parent.parent.name, data["digest"], "intent", GATE_OPEN_REASON)
    print(f"iaso: {args.intent}: the {args.stage} gate passed "
          f"({len(findings)} low finding(s) left)")
    _study_hint(root, path, data)
    return 0


def _study_hint(root: Path, path: Path, data: Mapping[str, Any]) -> None:
    """SR-293 EX-6: the step that starts picks its study on the agent's own initiative; nothing
    once the step has its idea."""
    from iaso import study

    if any(s.get("loop") == path.stem and s.get("step") == data["step"]
           for s in study.studies(root)):
        return
    print(f"iaso: pick the {data['step']} step's study: run iaso study candidates, then "
          "iaso study propose --title --why --depth for one idea, or nothing when nothing "
          "valuable stands out")


def cmd_done(core: Any, args: argparse.Namespace) -> int:
    from iaso.capture import proof

    root = Path(core.root)
    _intent(core, args.intent)
    path, data = _find(root, _session(args, root), args.intent)
    missing = [] if _passed(data, "plan") else ["the plan gate has not passed"]
    required = requirements_of(core, args.intent)
    if not required:     # SR-197 EX-2: nothing captured is no proof shown
        missing.append(f"no requirement derives from {args.intent}: no proof to show")
    missing += [f"{row['id']} ({row['title']}): proof {row['why']}"
                for row in proof.not_shown(core, required)]
    missing += [f"{row['id']} ({row['title']}): proof {row['why']} "
                f"(iaso evaluate proof {row['id']})" for row in proof.unverified(core, required)]
    if missing:
        _draw_proofs(core, data)    # the task the band keeps is the real state, not stale words
        _stop(path, data, "proof shown" if _passed(data, "plan") else "the plan gate")
        print(f"iaso: {args.intent} is not done; the intent stays open:", file=sys.stderr)
        for line in missing:
            print(f"  {line}", file=sys.stderr)
        return EXIT_FINDINGS
    data["stages"]["build"] = {"state": "passed", "at": _now()}
    data.update(tasks=None, stopped=None)   # step proven: the loop is closed, the band one line
    save(path, data)
    reset_head(root, path.parent.parent.name)
    core.log_append("events", "intent-done", {"intent": args.intent, "digest": data["digest"]})
    _clean_up(root, path, data)
    print(f"iaso: {args.intent} done: every proof shown (the records stay as they are)")
    return 0


def cmd_progress(core: Any, args: argparse.Namespace) -> int:
    """The current step's task in the owner's words, and how far it is (SR-291)."""
    root = Path(core.root)
    session = _session(args, root)
    found = [(p, d) for p, d in loops(root, session) if not _passed(d, "build")] if session else []
    if not found:
        # SR-291 EX-7: a workflow's agent may run under another session id (or none): the open
        # loop is the owning session's, so its band moves; two sessions' loops are ambiguous
        found = [(p, d) for p, d in loops(root) if not _passed(d, "build")]
        if len({p.parent.parent.name for p, _ in found}) > 1:
            raise LookupError("intent loops are open in more than one session: "
                              "name the session with --session")
    if not found:
        raise LookupError("no open intent loop in this session: iaso intent open comes first")
    if args.done is not None and args.done < 0 or args.total is not None and args.total < 1:
        raise ValueError("--done is 0 or more and --total 1 or more")
    path, data = found[-1]
    held = data.get("tasks") if isinstance(data.get("tasks"), Mapping) else {}
    data["tasks"] = {"label": args.task, "done": args.done or 0, "total": args.total,
                     "started_at": held.get("started_at") if held.get("label") == args.task
                     else _now(), "left": list(args.left or ())}
    save(path, data)
    total = f"/{args.total}" if args.total else ""
    print(f"iaso: {data['step']}: {args.task} · {args.done or 0}{total}")
    return 0


def _pane(core: Any, data: Mapping[str, Any]) -> dict[str, Any]:
    """SR-305: what the band's loop pane adds to the state: the records of the loop's intent
    (the intent and the requirements and decisions linked to it) by title, and each
    requirement's proof shown or not."""
    from iaso.capture import proof

    intent = data.get("intent")
    index = core.index()
    if not intent or intent not in index:
        return {"records": [], "proofs": []}
    linked = sorted(r.id for r in index.values() if any(
        link.kind in ("derives_from", "decides") and link.target.record == intent
        for link in r.links))
    required = requirements_of(core, intent)
    missing = {row["id"] for row in proof.not_shown(core, required)}
    return {"records": [{"id": i, "kind": index[i].kind, "title": index[i].title}
                        for i in [intent, *linked]],
            "proofs": [{"id": i, "title": index[i].title, "shown": i not in missing}
                       for i in required]}


def _clean_up(root: Path, path: Path, data: Mapping[str, Any]) -> None:
    """SR-308: remove the ended loop's own working files: the findings and plan files its gates
    were given, its state file and, when no other loop of its session is open, the session's
    judge results. Records and log entries stay."""
    import shutil

    session = path.parent.parent.name
    for name in data.get("files", ()):
        Path(name).unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    if any(not _passed(d, "build") and not d.get("handed_to") for _, d in loops(root, session)):
        return      # another loop of this session still needs them
    shutil.rmtree(files.results_dir(root, session), ignore_errors=True)


def cmd_status(core: Any, args: argparse.Namespace) -> int:
    root = Path(core.root)
    found = [(p, d) for p, d in loops(root, _session(args, root)) if not _passed(d, "build")
             and not d.get("handed_to")]
    if args.as_json:
        emit([{**d, **_pane(core, d)} for _, d in found], True)
        return 0
    for _, data in found:
        states = ", ".join(f"{s} {data['stages'].get(s, {}).get('state', 'open')}" for s in STAGES)
        print(f"{data.get('intent') or data['digest'].removeprefix('sha256:')[:12]}: {states}")
    if not found:
        print("iaso: no intent loop is open")
    return 0


def _checkouts(root: Path) -> list[Path]:
    """This checkout, then the main checkout when this is a worktree (SR-302 EX-2)."""
    from iaso.awareness import gitfiles

    common = gitfiles.common_dir(root)
    main = common.parent if common is not None and common.name == ".git" else root
    return [root, main] if main.resolve() != root.resolve() else [root]


def cmd_adopt(core: Any, args: argparse.Namespace) -> int:
    """SR-302: take over an open loop of another session: copy it into this session, mark the
    old copy handed over and open the old session's gate."""
    from iaso.api import open_core

    root = Path(core.root)
    session = _session(args, root)
    if session is None:
        print("iaso: name the session that takes the loop over with --session", file=sys.stderr)
        return EXIT_USAGE
    found = [(r, p, d) for r in _checkouts(root) for p, d in loops(r)
             if not d.get("handed_to") and not _passed(d, "build")
             and (r != root or p.parent.parent.name != session)
             and (not args.from_session or p.parent.parent.name == args.from_session)
             and (not args.intent or d.get("intent") == args.intent)
             and (not args.digest or str(d["digest"]).removeprefix("sha256:").startswith(
                 args.digest.removeprefix("sha256:")))]
    if not found:
        print("iaso: no open loop matches; nothing taken over", file=sys.stderr)
        return EXIT_FINDINGS
    if len(found) > 1:  # never guess: the others may be loops other sessions still run
        print("iaso: more than one open loop matches; name one with --from-session, --intent "
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
    from iaso.understand.loops import touch

    touch(root)
    held = gate.state(old_root, old_session)
    if held.state == "closed":
        gate.open(open_core(old_root), old_session, held.message_digest, "handover",
                  f"the loop was taken over by session {session}")
    print(f"iaso: {data.get('intent') or 'the loop'} taken over from session {old_session}")
    return 0


def run(command: str, argv: list[str]) -> int:
    if not argv or argv[0] not in LOOP_VERBS:
        from iaso.capture import cli as capture_cli

        return int(capture_cli.run(command, argv) or 0)
    parser = argparse.ArgumentParser(
        prog="iaso intent",
        description="The intent loop: open it on the owner's /iaso intent <words>, record "
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
    progress = verbs.add_parser("progress", help="the current step's task, as the band draws it")
    progress.add_argument("--task", required=True, metavar="WORDS")
    progress.add_argument("--done", type=int, default=None)
    progress.add_argument("--total", type=int, default=None)
    progress.add_argument("--left", action="append", metavar="WORDS",
                          help="a task still to do (repeat); the loop pane names them")
    adopter = verbs.add_parser("adopt")
    adopter.add_argument("--from-session", default=None)
    adopter.add_argument("--intent", default=None, metavar="INT-###")
    adopter.add_argument("--digest", default=None)
    for sub in (opener, gater, doner, verbs.choices["status"], progress, adopter):
        add_common(sub)
        sub.add_argument("--session", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    from iaso.api import open_core

    core = open_core(resolve_root(args.root))
    try:
        return {"open": cmd_open, "gate": cmd_gate, "done": cmd_done, "status": cmd_status,
                "progress": cmd_progress, "adopt": cmd_adopt}[
            args.verb](core, args)
    except (LookupError, ValueError) as exc:
        print(f"iaso: {exc}", file=sys.stderr)
        return EXIT_FINDINGS if isinstance(exc, LookupError) else EXIT_USAGE
