"""CORE commands: init, show, link, repin, validate, status, brief, explain (alias why), approve,
relay, revoke."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plumb.cliutil import EXIT_USAGE, add_common, emit, resolve_root

CONFIG_TEMPLATE = """\
# plumb configuration. Every key is optional; the defaults are shown commented out.
# A list given here replaces the default list.
# source_dirs: [src, tests]      # unset: also any code file outside tests, docs and dot dirs
# test_dirs: [tests]
# verify:
#   turn_budget_s: 15
#   hard_limit_factor: 1.5
#   fill_fraction: 0.65        # estimates (scaled by observed pace) fill 65 % of the budget
#   sample_size: 10
#   default_test_s: 1.0
#   workers: 0                 # 0 = no -n; at most 2
#   flaky_rerun: true
#   infra_globs: ["**/conftest.py", pyproject.toml, uv.lock, pytest.ini, tox.ini, setup.cfg]
# hooks:
#   budget_ms: {session_start: 1400, prompt: 1200, stop: 1400, post_edit: 300}
#   brief_lines: 30
#   prompt_lines: 20
#   prompt_tokens: 200         # per-prompt injection budget; records once per session
#   session_brief: compact     # compact (a few lines) | full (the long brief)
#   summary_proposed_cap: 3    # records shown in full per summary
# approve:
#   affirmations: [ok, okay, yes, approve, approved, confirm, confirmed, agreed, lgtm,
#                  go ahead, sounds good]
# judgment:
#   backend: heuristic         # heuristic | jev | disabled
#   hook_timeout_ms: 800
# escalation: {max_requirements: 3, max_features: 1, diff_lines: 400, diff_files: 10}
# trace:
#   exempt: []                 # source globs that need no requirement (untraced changes);
#                              # a glob added on a branch waits for plumb approve --exempt
"""

CLAIMS_TEMPLATE = """\
# SR: trailer policy (plumb trailers check-msg, plumb claims check).
require_trailer: false
# Extra exempt globs (the defaults .plumb/**, docs/**, .claude/**, uv.lock, .gitignore and
# .gitattributes always apply).
exempt: []
# NC-backed baseline of undeclared paths; it may only shrink: [{commit, path, nc}]
baseline: []
"""

GITIGNORE_LINES = ("cache/", "session/", "test_map.txt", "view/")
GITATTRIBUTES_LINES = ("log/*.jsonl merge=union",)
RECORD_DIRS = ("intents", "requirements", "decisions", "features", "ncs")


def _ensure_lines(path: Path, lines: tuple[str, ...]) -> bool:
    """Create ``path`` with ``lines`` or append the missing ones. True when it changed."""
    if path.exists():
        current = path.read_text(encoding="utf-8")
        present = {line.strip() for line in current.splitlines()}
        missing = [line for line in lines if line not in present]
        if not missing:
            return False
        prefix = "" if current.endswith("\n") or not current else "\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(prefix + "\n".join(missing) + "\n")
        return True
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return True


def init_repo(root: Path) -> list[str]:
    """Create ``.plumb/`` in ``root``; idempotent. Returns the paths created or changed."""
    from plumb.paths import PlumbPaths

    paths = PlumbPaths(root)
    changed: list[str] = []
    for directory in (*(paths.plumb / d for d in RECORD_DIRS), paths.log_dir):
        if not directory.is_dir():
            directory.mkdir(parents=True, exist_ok=True)
            changed.append(directory.relative_to(root).as_posix() + "/")
    for path, content in ((paths.config, CONFIG_TEMPLATE), (paths.claims, CLAIMS_TEMPLATE)):
        if not path.exists():
            path.write_text(content, encoding="utf-8", newline="\n")
            changed.append(path.relative_to(root).as_posix())
    for path, lines in ((paths.plumb / ".gitignore", GITIGNORE_LINES),
                        (paths.plumb / ".gitattributes", GITATTRIBUTES_LINES)):
        if _ensure_lines(path, lines):
            changed.append(path.relative_to(root).as_posix())
    # one file per log entry under .plumb/log/<kind>/ (SP6 6.5): no JSONL file is created;
    # GITATTRIBUTES_LINES keeps merge=union for legacy files during the transition
    return changed


# --------------------------------------------------------------------------- commands


def _parser(command: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"plumb {command}", description=description)
    add_common(parser)
    return parser


def cmd_init(command: str, argv: list[str]) -> int:
    parser = _parser(command, "Adopt this repository: create .plumb/ (idempotent).")
    args = parser.parse_args(argv)
    root = resolve_root(args.root)
    changed = init_repo(root)
    # sp6 7.1, 10 (R15, R17): adopting a repository also sets up the record merge driver
    # and the quick merge check (no test run) in git, when it is a git repository
    from plumb.hosts.claude_code.install import git_adoption

    git_lines: list[str] = []
    if (root / ".git").exists():
        git_adoption(root, sys.executable, git_lines, False)
        git_lines = [line for line in git_lines if not line.endswith("unchanged")]
    if args.as_json:
        emit({"root": str(root), "changed": changed, "git": git_lines}, True)
    elif changed or git_lines:
        emit([f"plumb: created {c}" for c in changed] + git_lines, False)
    else:
        print("plumb: already initialized")
    return 0


def _core(args: argparse.Namespace):
    from plumb.api import open_core

    return open_core(resolve_root(args.root))


def cmd_link(command: str, argv: list[str]) -> int:
    from plumb.links import LinkError, LinkUsageError, parse_cli_target

    parser = _parser(command, "Add a hash-pinned link from a record to a record or file.")
    parser.add_argument("source", help="source record ID")
    parser.add_argument("kind", help="derives_from, decides, upstream, relates_to, "
                        "implemented_by, verified_by, corrects, supersedes")
    parser.add_argument("target", help="record ID or repository-relative path")
    parser.add_argument("--example", default=None, help="EX-n or AC-n (verified_by)")
    args = parser.parse_args(argv)
    core = _core(args)
    try:
        target = parse_cli_target(args.target)
        link = core.add_link(args.source, args.kind, target, args.example)
    except LinkUsageError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    pin = link.pin
    data = {"link": link.id, "kind": link.kind, "target": args.target,
            "pin": None if pin is None else {"from": pin.source, "to": pin.target}}
    emit(data if args.as_json else f"plumb: linked {link.id} {link.kind} {args.target}",
         args.as_json)
    return 0


def cmd_repin(command: str, argv: list[str]) -> int:
    from plumb.links import LinkError, repin, repin_after_tests

    parser = _parser(command, "Refresh link pins (and pin unpinned links). Never confirms.")
    parser.add_argument("selector", nargs="?", help="link id (SR-003#2) or record ID")
    parser.add_argument("--all-stale", action="store_true", help="every stale or unpinned link")
    parser.add_argument("--after-tests", action="store_true",
                        help="rerun the linked tests and repin only when they pass and a model "
                             "judges the meaning unchanged; refuses otherwise")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if not args.selector and not args.all_stale:
        parser.error("name a link id, a record ID, or --all-stale")
    if args.after_tests and (not args.selector or args.all_stale):
        parser.error("--after-tests takes one link id or record ID")
    core = _core(args)
    refused: list[tuple[str, str]] = []
    try:
        if args.after_tests:
            outcome = repin_after_tests(core, args.selector)
            changes, refused = outcome.changes, outcome.refused
        else:
            changes = repin(core, args.selector, all_stale=args.all_stale, note=args.note)
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        emit({"repinned": changes, "refused": [{"link": link, "why": why}
                                               for link, why in refused]}, True)
    elif changes:
        emit([f"plumb: repinned {c['link']}" for c in changes], False)
    elif not refused:
        print("plumb: nothing to repin")
    if not args.as_json:
        for link, why in refused:
            print(f"plumb: refused to repin {link}: {why}", file=sys.stderr)
    return 1 if refused else 0


def cmd_stale(command: str, argv: list[str]) -> int:
    """``plumb stale card <link>``: bring a stale link to the owner as a card."""
    from plumb import stale

    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write("usage: plumb stale card <link> --topic TITLE --issue WORDS "
                         "--options a|b|c [--recommended N] [--session ID]" + chr(10) +
                         "Records a stale card for an owner-intent question: the link then "
                         "counts as resolved for the end-of-turn hold, and the end-of-turn "
                         "summary shows the card to the owner." + chr(10))
        return 0 if argv else EXIT_USAGE
    if argv[0] != "card":
        print(f"plumb: unknown stale command '{argv[0]}' (card)", file=sys.stderr)
        return EXIT_USAGE
    parser = _parser("plumb stale card", "Bring a stale link to the owner as a card.")
    parser.add_argument("link", help="the stale link id (SR-003#2)")
    parser.add_argument("--topic", required=True, help="the requirement's title")
    parser.add_argument("--issue", required=True, help="what changed, in the owner's words")
    parser.add_argument("--options", required=True,
                        help="the suggested resolutions, separated by |")
    parser.add_argument("--recommended", type=int, default=0,
                        help="which option (from 0) to suggest first")
    parser.add_argument("--session", default=None)
    args = parser.parse_args(argv[1:])
    options = [o.strip() for o in args.options.split("|") if o.strip()]
    if len(options) < 2 or not 0 <= args.recommended < len(options):
        print("plumb: give at least two --options separated by |, and a --recommended that "
              "is one of them", file=sys.stderr)
        return EXIT_USAGE
    core = _core(args)
    record_id, _, position = args.link.partition("#")
    record = core.index().get(record_id)
    if record is None or not position.isdigit() or int(position) >= len(record.links):
        print(f"plumb: no link {args.link}", file=sys.stderr)
        return 1
    from plumb.hashing import target_path

    target = record.links[int(position)].target
    path = target.record or target_path(target) or ""
    session = args.session or stale.current_session(core.root)
    card = stale.add_card(core.root, session, link=args.link, record=record_id, path=path,
                          topic=args.topic, issue=args.issue, options=options,
                          recommended=args.recommended, turn=stale.turn_number(core.root, session))
    emit({"card": card} if args.as_json else f"plumb: card recorded for {args.link}; the "
         "turn may end with it waiting for the owner", args.as_json)
    return 0


def _guarded(action: Callable[[], object]) -> int:
    from plumb.approvals import ApprovalError, Declined, Refused

    try:
        action()
    except Refused as exc:
        print(f"plumb: refused: {exc}", file=sys.stderr)
        return 3
    except ApprovalError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    except Declined as exc:
        print(f"{exc}")
        return 0
    return 0


def _approved_names(entry: Any) -> str:
    """``SR-001, trace.exempt src/gen/*``: what an approval entry confirmed."""
    names = [str(r["id"]) for r in entry.payload["records"]]
    if entry.payload.get("exempt"):
        names.append("trace.exempt " + " ".join(entry.payload["exempt"]))
    return ", ".join(names)


def cmd_approve(command: str, argv: list[str]) -> int:
    from plumb import approvals

    parser = _parser(command, "Owner approval of records at their current content, after a "
                     "y/N answered in the owner's own interactive terminal. Refused under the "
                     "agent session marker and outside an interactive terminal.")
    parser.add_argument("ids", nargs="*", help="record IDs")
    parser.add_argument("--proposed", action="store_true",
                        help="every proposed or unconfirmed-edit record")
    parser.add_argument("--exempt", action="store_true",
                        help="also confirm the trace.exempt globs of .plumb/config.yaml")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if not args.ids and not args.proposed and not args.exempt:
        parser.error("name record IDs or pass --proposed or --exempt")
    core = _core(args)

    def act() -> None:
        approvals.refuse_under_marker("approve")
        ids = list(args.ids)
        if args.proposed:
            listed = approvals.pending(core)
            if not listed and not ids and not args.exempt:
                print("plumb: nothing awaits your confirmation")
                return
            for record_id, record_hash, state in listed:
                title = core.index()[record_id].title
                print(f"  {record_id} {state} {record_hash[:19]}  {title}")
            ids += [r[0] for r in listed if r[0] not in ids]
        entry = approvals.approve(core, ids, note=args.note, exempt=args.exempt)  # asks y/N
        print(f"plumb: approved {_approved_names(entry)}")

    return _guarded(act)


def cmd_revoke(command: str, argv: list[str]) -> int:
    from plumb import approvals

    parser = _parser(command, "Owner revocation of the latest approval of records.")
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> None:
        entry = approvals.revoke(core, args.ids, note=args.note)
        print("plumb: revoked " + ", ".join(r["id"] for r in entry.payload["records"]))

    return _guarded(act)


def cmd_relay(command: str, argv: list[str]) -> int:
    from plumb import approvals

    parser = _parser(command, "Record an approval (or revocation) the owner gave in a prompt, "
                     "with the owner's exact words.")
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--prompt", required=True, help="prompt digest (12+ hex digits)")
    parser.add_argument("--quote", required=True, help="the owner's exact words")
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--exempt", action="store_true",
                        help="also confirm the trace.exempt globs (the quote names them)")
    parser.add_argument("--group", default=None,
                        help="the group the last reply offered (low-risk, from plumb triage)")
    parser.add_argument("--set", default=None, dest="set_anchor", metavar="INT",
                        help="the escalated spec whose set the reply presented")
    parser.add_argument("--reject", nargs="?", const="intent-change", default=None,
                        choices=("capture-error", "intent-change"),
                        help="relay the owner's rejection of the proposed records instead: "
                        "capture-error when the read-back misread their words (a calibration "
                        "'no'), intent-change otherwise (no label; also the bare flag)")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if not args.ids and not args.exempt and not args.group and not args.set_anchor:
        parser.error("name record IDs or pass --exempt, --group or --set")
    core = _core(args)

    def act() -> None:
        entry = approvals.relay(core, args.ids, prompt=args.prompt, quote=args.quote,
                                revoke=args.revoke, note=args.note, exempt=args.exempt,
                                group=args.group, set_anchor=args.set_anchor,
                                reject=args.reject)
        if args.reject:
            names = ", ".join(r["id"] for r in entry.payload["records"])
            print(f"plumb: rejected {names} ({args.reject}, agent-relayed); still proposed, "
                  f"recapture it on the owner's words \"{args.quote}\"")
            return
        verb = "revoked" if args.revoke else "confirmed"
        names = _approved_names(entry)
        what = (f" (group {args.group})" if args.group else
                f" (set {args.set_anchor})" if args.set_anchor else "")
        print(f"plumb: {verb} {names}{what} (agent-relayed) on the owner's words "
              f"\"{args.quote}\"")
        left_out = (entry.payload.get("triage") or {}).get("left_out") or []
        if left_out:
            print("plumb: changed since offered, left out: " + ", ".join(left_out))
        if entry.payload.get("self_recorded"):
            print("plumb: labelled self-recorded message: the prompt hook did not record "
                  "these words")

    return _guarded(act)


def cmd_validate(command: str, argv: list[str]) -> int:
    from plumb.merge import merge_check
    from plumb.validate import report

    parser = _parser(command, "Check records, links, logs and approvals. --merge BASE also "
                     "runs the merge-boundary checks (exit 4: waits for your confirmation).")
    parser.add_argument("--merge", metavar="BASE", default=None)
    args = parser.parse_args(argv)
    core = _core(args)
    if args.merge is not None and args.as_json:  # one JSON document for both parts
        import contextlib
        import io
        import json

        parts = []
        for step in (lambda: report(core, True)[0],
                     lambda: merge_check(core, args.merge, as_json=True)):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                parts.append((step(), buffer.getvalue()))
        (code, validate_out), (merge_code, merge_out) = parts
        try:
            merge_data = json.loads(merge_out)
        except ValueError:
            merge_data = {"error": merge_out.strip()}
        emit({"validate": json.loads(validate_out), "merge": merge_data}, True)
    else:
        code, _ = report(core, args.as_json)
        if args.merge is None:
            return code
        merge_code = merge_check(core, args.merge, as_json=args.as_json)
    if merge_code == EXIT_USAGE:
        return EXIT_USAGE
    return code or merge_code


def verification_state(core) -> dict | str:
    """VERIFY's state when that lane is built, else ``unavailable`` (spec 12.2)."""
    try:
        from plumb.verify import open_verify
    except ImportError:
        return "unavailable"
    try:
        pending = open_verify(core).full_pending()
    except Exception as exc:  # a missing or failing lane degrades, never fails status
        return {"available": False, "error": str(exc)}
    return {"available": True, "full_pending": pending.pending,
            "full_pending_reasons": list(pending.reasons)}


def acceptance_failures(core) -> dict:
    """Requirements whose acceptance tests fail (VERIFY), ``{}`` without that lane."""
    try:
        from plumb.verify import open_verify
    except ImportError:
        return {}
    try:
        return open_verify(core).requirement_failures()
    except Exception:  # a missing or failing lane degrades, never fails the command
        return {}


def _failing_text(record_id: str, item: dict) -> str:
    from plumb.merge import failing_line

    return failing_line(record_id, item)


def status_data(core) -> dict:
    from plumb.contracts import KIND_PREFIX

    index = core.index()
    statuses = core.status()
    records = dict.fromkeys(KIND_PREFIX, 0)
    for record in index.values():
        records[record.kind] += 1
    requirements = [s for i, s in statuses.items() if index[i].kind == "requirement"]
    confirmation = {"proposed": 0, "confirmed": 0, "unconfirmed-edit": 0}
    for status in statuses.values():
        confirmation[status.confirmation] += 1
    links = {"current": 0, "stale": 0, "dangling": 0, "unpinned": 0}
    for status in statuses.values():
        for state in status.links:
            links[state.state] += 1
    failing = acceptance_failures(core)
    return {
        "records": records,
        "requirements": {"total": len(requirements),
                         "confirmed": sum(s.confirmation == "confirmed" for s in requirements),
                         "covered": sum(s.covered for s in requirements),
                         "failing": len(failing)},
        "failing": failing,
        "confirmation": confirmation,
        "links": links,
        "stale": [s.link.id for st in statuses.values() for s in st.links if s.state == "stale"],
        "uncovered_examples": {i: list(s.uncovered_examples) for i, s in statuses.items()
                               if s.uncovered_examples and s.confirmation == "confirmed"},
        "awaiting": sorted(i for i, s in statuses.items() if s.confirmation != "confirmed"),
        "changed_tests": {i: list(s.changed_tests) for i, s in sorted(statuses.items())
                          if s.changed_tests},
        "verification": verification_state(core),
    }


def _awareness_section(args: argparse.Namespace) -> list[str]:
    """sp6 9.4 (SR-078): every record other worktrees and branches are changing, with the
    worktree paths, and other branches' intent in flight."""
    try:
        from plumb.awareness.lines import status_section

        return status_section(_core(args))
    except Exception:  # noqa: BLE001 - awareness is advisory
        return []


def cmd_status(command: str, argv: list[str]) -> int:
    parser = _parser(command, "Counts, drift and records awaiting your confirmation.")
    args = parser.parse_args(argv)
    data = status_data(_core(args))
    if args.as_json:
        try:
            from plumb.awareness.lines import status_data as elsewhere

            data["elsewhere"] = elsewhere(_core(args))["overlaps"]
        except Exception:  # noqa: BLE001 - awareness is advisory
            pass
        emit(data, True)
        return 0
    kinds = ", ".join(f"{k} {v}" for k, v in data["records"].items())
    req = data["requirements"]
    conf = data["confirmation"]
    links = data["links"]
    lines = [
        f"records: {kinds}",
        f"requirements: {req['total']} total, {req['confirmed']} confirmed, "
        f"{req['covered']} covered"
        + (f", {req['failing']} failing ({', '.join(data['failing'])})"
           if req["failing"] else ""),
        f"confirmation: proposed {conf['proposed']}, confirmed {conf['confirmed']}, "
        f"unconfirmed edit {conf['unconfirmed-edit']}",
        f"links: current {links['current']}, stale {links['stale']}, dangling "
        f"{links['dangling']}, unpinned {links['unpinned']}",
        "awaiting your confirmation: " + (", ".join(data["awaiting"]) or "none"),
    ]
    for record_id, ends in data["changed_tests"].items():
        lines.append(f"acceptance test changed since you confirmed it: {record_id} "
                     + ", ".join(ends))
    if data["stale"]:
        lines.append("stale links: " + ", ".join(data["stale"]))
    for record_id, items in data["failing"].items():
        lines.extend("failing acceptance tests: " + _failing_text(record_id, item)
                     for item in items)
    verification = data["verification"]
    if verification == "unavailable" or not verification.get("available"):
        lines.append("verification: unavailable")
    elif verification.get("full_pending"):
        lines.append("verification: full verification pending ("
                     + ", ".join(verification["full_pending_reasons"]) + ")")
    else:
        lines.append("verification: no full verification pending")
    lines += _awareness_section(args)
    emit(lines, False)
    return 0


def cmd_brief(command: str, argv: list[str]) -> int:
    from plumb.query import HARD_CAP, brief_lines

    parser = _parser(command, "The short intent brief (about 30 lines, cap 40).")
    parser.add_argument("--max-lines", type=int, default=None)
    parser.add_argument("--all", action="store_true", dest="show_all")
    args = parser.parse_args(argv)
    core = _core(args)
    max_lines = args.max_lines or core.config.hooks.brief_lines
    if args.show_all:
        max_lines = 10**6
    lines = brief_lines(core, max_lines, show_all=args.show_all)
    verification = verification_state(core)
    if verification == "unavailable":
        tests = "tests: verification unavailable in this build"
    elif verification.get("full_pending"):
        tests = "tests: full verification pending (" + ", ".join(
            verification.get("full_pending_reasons") or []) + ")"
    else:
        tests = None
    if tests and (args.show_all or len(lines) < min(max_lines, HARD_CAP)):
        lines.insert(len(lines) - 1 if lines[-1].startswith("open NCs") else len(lines), tests)
    emit({"lines": lines} if args.as_json else lines, args.as_json)
    return 0


def _target_label(target) -> str:
    return target.record or target.test or target.path or target.symbol or "?"


def drift_data(core) -> dict:
    """The drift signals (spec 5.10): stale and dangling links with the moved end,
    unconfirmed edits, uncovered examples, failing acceptance tests (a requirement's tests
    whose last run failed, regressions included), and fidelity that a judgment no longer
    covers.

    A requirement never judged is advisory only (R4: fidelity is on demand or listed at the
    merge boundary); it is returned under ``never_judged`` and is not a drift signal.
    """
    index = core.index()
    statuses = core.status()
    stale: list[dict] = []
    dangling: list[dict] = []
    for record_id in sorted(statuses):
        for state in statuses[record_id].links:
            label = _target_label(state.link.target)
            if state.state == "stale":
                stale.append({"link": state.link.id, "moved": state.moved, "target": label})
            elif state.state == "dangling":
                dangling.append({"link": state.link.id, "target": label})
    unconfirmed = sorted(i for i, s in statuses.items() if s.confirmation == "unconfirmed-edit")
    changed_tests = {i: list(s.changed_tests) for i, s in sorted(statuses.items())
                     if s.changed_tests}
    uncovered = {i: list(s.uncovered_examples) for i, s in sorted(statuses.items())
                 if index[i].kind == "requirement" and s.uncovered_examples}
    fidelity: list[dict] | str
    never_judged: list[str] = []
    try:
        from plumb.judgment.fidelity import fidelity_state, latest_judgments
    except ImportError:
        fidelity = "unavailable"
    else:
        fidelity = []
        latest = latest_judgments(core)
        for record_id in sorted(index):
            record = index[record_id]
            if record.kind != "requirement":
                continue
            state = fidelity_state(core, record, latest)
            if state is None or state == "fits":
                continue
            if record_id not in latest:
                never_judged.append(record_id)
            else:
                fidelity.append({"requirement": record_id, "state": state})
    fidelity_signals = fidelity if isinstance(fidelity, list) else []
    failing = acceptance_failures(core)
    clean = not (stale or dangling or unconfirmed or uncovered or fidelity_signals or failing)
    return {"clean": clean, "stale": stale, "dangling": dangling, "failing": failing,
            "unconfirmed_edits": unconfirmed, "changed_tests": changed_tests,
            "uncovered_examples": uncovered,
            "fidelity": fidelity, "never_judged": never_judged, "hints": drift_hint_lines(core)}


def drift_hint_lines(core) -> list[str]:
    """Hints only (sp2 10): hidden dependencies and proposed test nodes. Never drift
    signals: they change neither ``clean`` nor the exit code."""
    try:
        from plumb.capture.hints import changed_paths, drift_hints

        return drift_hints(core, changed_paths(core), all_nodes=True)
    except Exception:  # noqa: BLE001 - advisory; a missing lane never fails drift
        return []


def cmd_drift(command: str, argv: list[str]) -> int:
    parser = _parser(command, "Drift signals only: stale and dangling links, unconfirmed "
                     "edits, uncovered examples, fidelity a judgment no longer covers.")
    args = parser.parse_args(argv)
    data = drift_data(_core(args))
    code = 0 if data["clean"] else 1
    if args.as_json:
        emit(data, True)
        return code
    lines: list[str] = []
    for item in data["stale"]:
        lines.append(f"{item['link']} stale ({item['moved']} moved: {item['target']})")
    for item in data["dangling"]:
        lines.append(f"{item['link']} dangling (missing: {item['target']})")
    for record_id in data["unconfirmed_edits"]:
        ends = data["changed_tests"].get(record_id)
        if ends:
            lines.append(f"{record_id} acceptance test changed since you confirmed it: "
                         f"{', '.join(ends)} (plumb validate --merge shows the diff)")
        else:
            lines.append(f"{record_id} unconfirmed edit (approved content changed)")
    for record_id, examples in data["uncovered_examples"].items():
        lines.append(f"{record_id} uncovered examples: {', '.join(examples)}")
    for record_id, items in data["failing"].items():
        for item in items:
            text = _failing_text(record_id, item).removeprefix(record_id + " ")
            lines.append(f"{record_id} failing acceptance test: {text}")
    if data["fidelity"] == "unavailable":
        lines.append("fidelity: unavailable")
    else:
        for item in data["fidelity"]:
            lines.append(f"{item['requirement']} fidelity {item['state']} "
                         f"(plumb fidelity {item['requirement']})")
    if not lines:
        lines.append("drift: none")
    lines.extend(data.get("hints") or [])
    if data["never_judged"]:
        lines.append(f"advisory: fidelity never judged for {len(data['never_judged'])} "
                     "requirements (listed at the merge boundary; plumb fidelity <SR>)")
    emit(lines, False)
    return code


def cmd_show(command: str, argv: list[str]) -> int:
    from plumb.readback import show_lines

    parser = _parser(command, "Print records in full: the read-back, will/won't, labelled "
                     "assumptions, every example, the alternatives and the body.")
    parser.add_argument("ids", nargs="+", metavar="ID")
    args = parser.parse_args(argv)
    lines, missing = show_lines(_core(args), args.ids)
    for record_id in missing:
        print(f"plumb: no record {record_id}", file=sys.stderr)
    emit({"lines": lines, "missing": missing} if args.as_json else lines, args.as_json)
    return 1 if missing else 0


def cmd_explain(command: str, argv: list[str]) -> int:
    from plumb.explain import explain_lines

    parser = _parser(command, "Why a behaviour, a file or a record exists, in plain terms: "
                     "the requirement, the owner's words it comes from, decisions, examples, "
                     "test state and code. Takes plain words, a path or a record ID.")
    parser.add_argument("query", nargs="+", help="plain words, a file path or a record ID")
    args = parser.parse_args(argv)
    lines, data = explain_lines(_core(args), " ".join(args.query))
    emit({**data, "lines": lines} if args.as_json else lines, args.as_json)
    return 0 if data["records"] else 1


def _not_built(command: str, argv: list[str]) -> int:
    print(f"plumb: '{command}' is not available in this build", file=sys.stderr)
    return EXIT_USAGE


HANDLERS: dict[str, Callable[[str, list[str]], int]] = {
    "init": cmd_init,
    "show": cmd_show,
    "link": cmd_link,
    "repin": cmd_repin,
    "stale": cmd_stale,
    "approve": cmd_approve,
    "revoke": cmd_revoke,
    "relay": cmd_relay,
    "validate": cmd_validate,
    "check": cmd_validate,
    "status": cmd_status,
    "brief": cmd_brief,
    "drift": cmd_drift,
    "explain": cmd_explain,
    "why": cmd_explain,  # the earlier name; explain takes plain words too
}


def run(command: str, argv: list[str]) -> int:
    handler = HANDLERS.get(command, _not_built)
    try:
        return handler(command, argv)
    except SystemExit as exc:  # argparse usage errors and --help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
