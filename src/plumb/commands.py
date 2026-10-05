"""CORE commands: init, link, repin, validate, status, brief, approve, relay, revoke."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from plumb.cliutil import EXIT_USAGE, add_common, emit, resolve_root

CONFIG_TEMPLATE = """\
# plumb configuration. Every key is optional; the defaults are shown commented out.
# A list given here replaces the default list.
# source_dirs: [src, tests]
# test_dirs: [tests]
# verify:
#   turn_budget_s: 15
#   hard_limit_factor: 1.5
#   sample_size: 10
#   default_test_s: 1.0
#   workers: 0                 # 0 = no -n; at most 2
#   flaky_rerun: true
#   infra_globs: ["**/conftest.py", pyproject.toml, uv.lock, pytest.ini, tox.ini, setup.cfg]
# hooks:
#   budget_ms: {session_start: 900, prompt: 600, stop: 800, post_edit: 300}
#   brief_lines: 30
#   prompt_lines: 20
#   summary_proposed_cap: 3
# approve:
#   affirmations: [ok, okay, yes, approve, approved, confirm, confirmed, agreed, lgtm,
#                  go ahead, sounds good]
# judgment:
#   backend: heuristic         # heuristic | jev | disabled
#   hook_timeout_ms: 800
# escalation: {max_requirements: 3, max_features: 1, diff_lines: 400, diff_files: 10}
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

GITIGNORE_LINES = ("cache/", "session/", "test_map.txt")
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
    for log in (paths.log_events, paths.log_evidence):
        if not log.exists():
            log.touch()
            changed.append(log.relative_to(root).as_posix())
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
    if args.as_json:
        emit({"root": str(root), "changed": changed}, True)
    elif changed:
        emit([f"plumb: created {c}" for c in changed], False)
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
    from plumb.links import LinkError, repin

    parser = _parser(command, "Refresh link pins (and pin unpinned links). Never confirms.")
    parser.add_argument("selector", nargs="?", help="link id (SR-003#2) or record ID")
    parser.add_argument("--all-stale", action="store_true", help="every stale or unpinned link")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if not args.selector and not args.all_stale:
        parser.error("name a link id, a record ID, or --all-stale")
    core = _core(args)
    try:
        changes = repin(core, args.selector, all_stale=args.all_stale, note=args.note)
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        emit({"repinned": changes}, True)
    elif changes:
        emit([f"plumb: repinned {c['link']}" for c in changes], False)
    else:
        print("plumb: nothing to repin")
    return 0


def _guarded(action: Callable[[], object]) -> int:
    from plumb.approvals import ApprovalError, Refused

    try:
        action()
    except Refused as exc:
        print(f"plumb: refused: {exc}", file=sys.stderr)
        return 3
    except ApprovalError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_approve(command: str, argv: list[str]) -> int:
    from plumb import approvals

    parser = _parser(command, "Owner approval of records at their current content. Refused "
                     "while the agent session marker is set.")
    parser.add_argument("ids", nargs="*", help="record IDs")
    parser.add_argument("--proposed", action="store_true",
                        help="every proposed or unconfirmed-edit record")
    parser.add_argument("--yes", action="store_true", help="do not ask y/N")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if not args.ids and not args.proposed:
        parser.error("name record IDs or pass --proposed")
    core = _core(args)

    def act() -> None:
        approvals.refuse_under_marker("approve")
        ids = list(args.ids)
        if args.proposed:
            listed = approvals.pending(core)
            if not listed and not ids:
                print("plumb: nothing awaits your confirmation")
                return
            for record_id, record_hash, state in listed:
                title = core.index()[record_id].title
                print(f"  {record_id} {state} {record_hash[:19]}  {title}")
            if not args.yes:
                if not sys.stdin.isatty():
                    raise SystemExit(EXIT_USAGE)
                answer = input(f"approve these {len(listed)} records? [y/N] ")
                if answer.strip().lower() not in ("y", "yes"):
                    print("plumb: nothing approved")
                    return
            ids += [r[0] for r in listed if r[0] not in ids]
        entry = approvals.approve(core, ids, note=args.note)
        names = ", ".join(r["id"] for r in entry.payload["records"])
        print(f"plumb: approved {names}")

    try:
        return _guarded(act)
    except SystemExit:
        print("plumb: not a terminal; pass --yes to approve the listed records",
              file=sys.stderr)
        return EXIT_USAGE


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
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--prompt", required=True, help="prompt digest (12+ hex digits)")
    parser.add_argument("--quote", required=True, help="the owner's exact words")
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    core = _core(args)

    def act() -> None:
        entry = approvals.relay(core, args.ids, prompt=args.prompt, quote=args.quote,
                                revoke=args.revoke, note=args.note)
        verb = "revoked" if args.revoke else "confirmed"
        names = ", ".join(r["id"] for r in entry.payload["records"])
        print(f"plumb: {verb} {names} (agent-relayed) on the owner's words \"{args.quote}\"")

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
    return {
        "records": records,
        "requirements": {"total": len(requirements),
                         "confirmed": sum(s.confirmation == "confirmed" for s in requirements),
                         "covered": sum(s.covered for s in requirements)},
        "confirmation": confirmation,
        "links": links,
        "stale": [s.link.id for st in statuses.values() for s in st.links if s.state == "stale"],
        "uncovered_examples": {i: list(s.uncovered_examples) for i, s in statuses.items()
                               if s.uncovered_examples and s.confirmation == "confirmed"},
        "awaiting": sorted(i for i, s in statuses.items() if s.confirmation != "confirmed"),
        "verification": verification_state(core),
    }


def cmd_status(command: str, argv: list[str]) -> int:
    parser = _parser(command, "Counts, drift and records awaiting your confirmation.")
    args = parser.parse_args(argv)
    data = status_data(_core(args))
    if args.as_json:
        emit(data, True)
        return 0
    kinds = ", ".join(f"{k} {v}" for k, v in data["records"].items())
    req = data["requirements"]
    conf = data["confirmation"]
    links = data["links"]
    lines = [
        f"records: {kinds}",
        f"requirements: {req['total']} total, {req['confirmed']} confirmed, "
        f"{req['covered']} covered",
        f"confirmation: proposed {conf['proposed']}, confirmed {conf['confirmed']}, "
        f"unconfirmed edit {conf['unconfirmed-edit']}",
        f"links: current {links['current']}, stale {links['stale']}, dangling "
        f"{links['dangling']}, unpinned {links['unpinned']}",
        "awaiting your confirmation: " + (", ".join(data["awaiting"]) or "none"),
    ]
    if data["stale"]:
        lines.append("stale links: " + ", ".join(data["stale"]))
    verification = data["verification"]
    if verification == "unavailable" or not verification.get("available"):
        lines.append("verification: unavailable")
    elif verification.get("full_pending"):
        lines.append("verification: full verification pending ("
                     + ", ".join(verification["full_pending_reasons"]) + ")")
    else:
        lines.append("verification: no full verification pending")
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


def _not_built(command: str, argv: list[str]) -> int:
    print(f"plumb: '{command}' is not available in this build", file=sys.stderr)
    return EXIT_USAGE


HANDLERS: dict[str, Callable[[str, list[str]], int]] = {
    "init": cmd_init,
    "link": cmd_link,
    "repin": cmd_repin,
    "approve": cmd_approve,
    "revoke": cmd_revoke,
    "relay": cmd_relay,
    "validate": cmd_validate,
    "check": cmd_validate,
    "status": cmd_status,
    "brief": cmd_brief,
}


def run(command: str, argv: list[str]) -> int:
    handler = HANDLERS.get(command, _not_built)
    try:
        return handler(command, argv)
    except SystemExit as exc:  # argparse usage errors and --help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
