"""CORE commands: init, show, link, repin, validate, status, brief, explain (alias why); approve,
revoke and relay are refused as gone (SR-210)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plumb.cliutil import EXIT_REFUSED, EXIT_USAGE, add_common, emit, resolve_root

CONFIG_TEMPLATE = """\
# plumb configuration. Every key is optional; the defaults are shown commented out.
# A list given here replaces the default list.
# source_dirs: [src, tests]      # unset: also any code file outside tests, docs and dot dirs
# test_dirs: [tests]
# verify:
#   turn_budget_s: 60
#   hard_limit_factor: 1.5
#   fill_fraction: 0.65        # estimates (scaled by observed pace) fill 65 % of the budget
#   sample_size: 10
#   default_test_s: 1.0
#   workers: 0                 # 0 = no -n; at most 2
#   flaky_rerun: true
#   infra_globs: ["**/conftest.py", pyproject.toml, uv.lock, pytest.ini, tox.ini, setup.cfg]
# hooks:
#   hard_limit_s: 90           # the watchdog cuts a hook here; at most 119 (host timeouts 120 s)
#   budget_ms: {session_start: 60000, prompt: 60000, stop: 60000, post_edit: 15000}
#   brief_lines: 30
#   prompt_lines: 20
#   prompt_tokens: 200         # per-prompt injection budget; records once per session
#   summary_proposed_cap: 3    # records shown in full per summary
# approve:
#   affirmations: [ok, okay, yes, approve, approved, confirm, confirmed, agreed, lgtm,
#                  go ahead, sounds good]
# judgment:
#   backend: jev               # jev | disabled; none set: judging raises an error
#   hook_timeout_ms: 800
# escalation: {max_requirements: 3, max_features: 1, diff_lines: 400, diff_files: 10}
# trace:
#   exempt: []                 # source globs that need no requirement (untraced changes);
#                              # a glob added on a branch is honoured at the merge and
#                              # listed; the judge accepts it unless it contradicts you (SR-288)
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

def _gitignore_lines() -> tuple[str, ...]:
    """SR-376, SR-321: the local kinds (DEC-116's owner words among them), then telemetry."""
    from plumb.log import LOCAL_KINDS

    return ("cache/", "session/", "test_map.txt", "view/",
            *(f"log/{kind}/" for kind in sorted(LOCAL_KINDS)), "log/judgment/*.json")


GITIGNORE_LINES = _gitignore_lines()
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
    from plumb import launcher
    from plumb.hosts.claude_code.install import git_adoption

    git_lines: list[str] = []
    plugin = launcher.plugin_root() is not None
    if (root / ".git").exists():
        if plugin:
            # SP7 4.5 (SR-083): under the plugin init also writes the commit check, each hook
            # calling the user-level launcher; nothing under .claude/ is written
            from plumb.hosts.claude_code.install import commit_msg_adoption

            commit_msg_adoption(root, sys.executable, git_lines)
        git_adoption(root, sys.executable, git_lines, False)
        git_lines = [line for line in git_lines if not line.endswith("unchanged")]
    if plugin and not args.as_json:
        from plumb.present import owner_text

        kept = [line for line in git_lines if "was kept" in line or "not installed" in line]
        emit([owner_text.INIT_DONE] + kept, False)
        return 0
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
    from plumb.links import LinkError, LinkUsageError, live_examples, parse_cli_target

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
        live = live_examples(core, target.record, args.source) if (
            args.kind == "supersedes" and target.record) else []
        link = core.add_link(args.source, args.kind, target, args.example)
    except LinkUsageError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    for ex, test in live:  # SR-164: print only, never refuse
        print(f"plumb: {target.record}/{ex} is still verified by {test}: retire the test too "
              f"(plumb unlink; drop it when it covers nothing else), DEC-065")
    pin = link.pin
    data = {"link": link.id, "kind": link.kind, "target": args.target,
            "pin": None if pin is None else {"from": pin.source, "to": pin.target}}
    emit(data if args.as_json else f"plumb: linked {link.id} {link.kind} {args.target}",
         args.as_json)
    return 0


def cmd_unlink(command: str, argv: list[str]) -> int:
    from plumb.links import LinkError, unlink

    parser = _parser(command, "Remove one link; the links after it move down by one.")
    parser.add_argument("link", help="link id (SR-003#2)")
    parser.add_argument("--note", required=True, help="why the link goes (logged)")
    args = parser.parse_args(argv)
    try:
        result = unlink(_core(args), args.link, args.note)
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    lines = [f"plumb: unlinked {result['link']} {result['kind']} {result['target']}"]
    lines += [f"plumb: {r['from']} is now {r['to']}" for r in result["renumbered"]]
    if result["untested"]:
        lines.append(f"plumb: {args.link.partition('#')[0]} {result['untested']} "
                     f"now has no test")
    emit(result if args.as_json else lines, args.as_json)
    return 0


def cmd_relink(command: str, argv: list[str]) -> int:
    from plumb.links import LinkError, LinkUsageError, parse_cli_target, relink

    parser = _parser(command, "Point one link at a new target, keeping its number, kind and "
                              "example, with fresh pins.")
    parser.add_argument("link", help="link id (SR-003#2)")
    parser.add_argument("target", help="record ID or repository-relative path")
    parser.add_argument("--note", required=True, help="why the link moves (logged)")
    args = parser.parse_args(argv)
    try:
        result = relink(_core(args), args.link, parse_cli_target(args.target), args.note)
    except LinkUsageError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    emit(result if args.as_json else
         f"plumb: relinked {result['link']} {result['old']['target']} -> "
         f"{result['new']['target']}", args.as_json)
    return 0


def cmd_repin(command: str, argv: list[str]) -> int:
    from plumb.links import LinkError, repin, repin_after_tests

    parser = _parser(command, "Refresh link pins (and pin unpinned links). Never confirms.")
    parser.add_argument("selector", nargs="?", help="link id (SR-003#2) or record ID")
    parser.add_argument("--all-stale", action="store_true", help="every stale or unpinned link")
    parser.add_argument("--after-tests", action="store_true",
                        help="rerun the linked tests and repin only when they pass and a model "
                             "judges the meaning unchanged; refuses otherwise")
    parser.add_argument("--dry-run", action="store_true",
                        help="change nothing (no record file, no log entry) and list what it "
                             "would repin; with --after-tests it asks the models only (JEV, "
                             "Sonnet and the Opus diagnosis; no tests, no card)")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if not args.selector and not args.all_stale:
        parser.error("name a link id, a record ID, or --all-stale")
    if args.after_tests and (not args.selector or args.all_stale):
        parser.error("--after-tests takes one link id or record ID")
    core = _core(args)
    refused: list[tuple[str, str]] = []
    would: list[tuple[str, str]] = []
    diagnoses: list[dict[str, Any]] = []
    try:
        if args.after_tests:
            from plumb.heavy import heavy

            with heavy(core.root, "plumb repin --after-tests"):
                outcome = repin_after_tests(core, args.selector, dry_run=args.dry_run)
            changes, refused, would = outcome.changes, outcome.refused, outcome.would
            diagnoses = outcome.diagnoses
        else:
            changes = repin(core, args.selector, all_stale=args.all_stale, note=args.note,
                            dry_run=args.dry_run)
            if args.dry_run:   # nothing was written: what it would do is the answer
                would = [(c["link"], "its pin would be refreshed") for c in changes]
                changes = []
    except LinkError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        emit({"repinned": changes, "refused": [{"link": link, "why": why}
                                               for link, why in refused],
              "would_repin": [{"link": link, "why": why} for link, why in would],
              "diagnoses": diagnoses}, True)
        return 1 if refused else 0
    for item in diagnoses:   # SR-114: what Opus found for a link Sonnet says changed
        print(_diagnosis_line(item, args.dry_run))
        consequences = item.get("consequences") or []
        for n, option in enumerate(item["options"], start=1):
            print(f"plumb:   {n}. {option}")
            if n <= len(consequences):
                print(f"plumb:      does and leaves undone: {consequences[n - 1]}")
        if item.get("why"):
            print(f"plumb:   why 1: {item['why']}")
    if would:
        emit([f"plumb: would repin {link}: {why}" for link, why in would], False)
    elif changes:
        emit([f"plumb: repinned {c['link']}" for c in changes], False)
    elif not refused:
        print("plumb: nothing to repin")
    for link, why in refused:
        print(f"plumb: refused to repin {link}: {why}", file=sys.stderr)
    return 1 if refused else 0


DIAGNOSIS_LINES = {
    "owner": "plumb: {link} needs the owner{card}: {topic}: {explanation}",
    "reword": "plumb: {link}: reword {record} to agree with its intent: {wording}",
    "back-to-development": "plumb: {link}: send the change back to development: {explanation}",
    "contradicts": "plumb: {link} now contradicts {other}{card}: {topic}: {explanation}",
}


def _diagnosis_line(item: dict[str, Any], dry_run: bool) -> str:
    card = " (card filed)" if item.get("card") else (" (dry run: no card filed)" if dry_run
                                                     else "")
    return DIAGNOSIS_LINES[item["outcome"]].format(
        link=item["link"], card=card, topic=item["topic"], explanation=item["explanation"],
        record=item["record"], wording=item["proposed_wording"], other=item.get("other", ""))


STALE_USAGE = (
    "usage: plumb stale card <link> --topic TITLE --issue WORDS --options a|b|c "
    "--consequences a|b|c --why REASON [--recommended N] [--session ID]\n"
    "       plumb stale cards [--incomplete] [--session ID] [--json]\n"
    "card: files a stale link's owner-intent question in plumb's internal store (the agent "
    "asks it with the question tool; nothing is shown to the owner as a card): the link then "
    "counts as resolved for the end-of-turn hold. Each option needs what it does and leaves "
    "undone (--consequences, one per option, "
    "in the same order) and the recommended one needs its reason (--why); a card lacking any "
    "is refused (SR-116). Re-filing a link's open card keeps its topic, issue and options "
    "unless given again; --recommended (numbered from 1) and --consequences need --options "
    "given with them. The record's wording, the change and the owner's words are added by "
    "plumb.\n"
    "cards: lists the open stale cards with all they show the owner; --incomplete lists only "
    "those still lacking something, and what.\n")


def _split(raw: str | None) -> list[str]:
    return [o.strip() for o in (raw or "").split("|") if o.strip()]


def cmd_stale(command: str, argv: list[str]) -> int:
    """``plumb stale card <link>``: bring a stale link to the owner as a card;
    ``plumb stale cards``: list the open ones with everything they show (SR-116)."""
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(STALE_USAGE)
        return 0 if argv else EXIT_USAGE
    if argv[0] == "cards":
        return _stale_cards(argv[1:])
    if argv[0] != "card":
        print(f"plumb: unknown stale command '{argv[0]}' (card, cards)", file=sys.stderr)
        return EXIT_USAGE
    return _stale_card(argv[1:])


def _stale_card(argv: list[str]) -> int:
    from plumb import stale

    parser = _parser("stale card", "Bring a stale link to the owner as a card.")
    parser.add_argument("link", help="the stale link id (SR-003#2)")
    parser.add_argument("--topic", default=None, help="the requirement's title")
    parser.add_argument("--issue", default=None, help="what changed, in the owner's words")
    parser.add_argument("--options", default=None,
                        help="the suggested resolutions, separated by |")
    parser.add_argument("--consequences", default=None,
                        help="for each option, in order and separated by |, what it does and "
                             "what it leaves undone")
    parser.add_argument("--why", default=None, help="why the recommended option is recommended")
    parser.add_argument("--recommended", type=int, default=None,
                        help="which option (numbered from 1, in the order of --options) to "
                             "recommend")
    parser.add_argument("--session", default=None)
    args = parser.parse_args(argv)
    core = _core(args)
    record_id, _, position = args.link.partition("#")
    record = core.index().get(record_id)
    if record is None or not position.isdigit() or int(position) >= len(record.links):
        print(f"plumb: no link {args.link}", file=sys.stderr)
        return 1
    session = args.session or stale.current_session(core.root)
    kept = stale.open_card(core.root, session, args.link) or {}
    options = _split(args.options) if args.options is not None else \
        [str(o) for o in kept.get("options") or ()]
    if args.options is None and options and (args.recommended is not None
                                             or args.consequences is not None):
        # --recommended and --consequences follow the order of --options: bound to the kept
        # card's order, which the agent does not see, they could recommend the option the
        # reason argues against (eval-0cf3090d). Refuse and say the order to give them in.
        kept_order = "; ".join(f"{n}. {o}" for n, o in enumerate(options, start=1))
        print(f"plumb: --recommended and --consequences follow the order of --options; the "
              f"open card for {args.link} has the options {kept_order}. Give --options again "
              "with them, in the order --recommended and --consequences mean", file=sys.stderr)
        return EXIT_USAGE
    # --recommended counts from 1, as the card numbers its options; stored from 0
    recommended = args.recommended - 1 if args.recommended is not None else \
        int(kept.get("recommended") or 0) if args.options is None else 0
    if len(options) < 2 or not 0 <= recommended < len(options):
        print("plumb: give at least two --options separated by |, and a --recommended that "
              "is one of them", file=sys.stderr)
        return EXIT_USAGE
    consequences = _split(args.consequences) if args.consequences is not None else \
        [str(c) for c in kept.get("consequences") or ()] if args.options is None else []
    from plumb.hashing import target_path

    target = record.links[int(position)].target
    entry = {"link": args.link, "record": record_id,
             "path": target.record or target_path(target) or "",
             "topic": args.topic if args.topic is not None else str(kept.get("topic") or ""),
             "issue": args.issue if args.issue is not None else str(kept.get("issue") or ""),
             "options": options, "recommended": recommended, "consequences": consequences,
             "why": (args.why if args.why is not None else str(kept.get("why") or "")).strip()}
    missing = stale.card_missing(entry)
    if consequences and len(consequences) != len(options):
        missing.insert(0, f"--consequences gives {len(consequences)} for {len(options)} "
                          "options: give one per option, in the same order")
    if missing:
        print(f"plumb: card for {args.link} refused as incomplete (SR-116): it lacks "
              + "; ".join(missing), file=sys.stderr)
        return EXIT_USAGE
    turn = int(kept.get("turn") or 0) or stale.turn_number(core.root, session)
    card = stale.add_card(core.root, session, turn=turn, by=str(kept.get("by") or ""),
                          **entry)
    # say the filed order and the recommended one back
    filed = "; ".join(f"{n}. {o}" for n, o in enumerate(options, start=1))
    emit({"card": card, "session": session} if args.as_json else
         f"plumb: question filed for {args.link} in session {session}; ask the owner with the "
         f"question tool. Options in the order filed: {filed}. Recommended: "
         f"{recommended + 1} ({options[recommended]})", args.as_json)
    return 0


def _stale_cards(argv: list[str]) -> int:
    from plumb import stale

    parser = _parser("stale cards", "List the open stale cards with all they show the owner.")
    parser.add_argument("--incomplete", action="store_true",
                        help="only the cards still lacking something (SR-116), and what")
    parser.add_argument("--session", default=None, help="one session (default: every one)")
    args = parser.parse_args(argv)
    core = _core(args)
    found = [(session, entry)
             for session in ([args.session] if args.session else stale.sessions(core.root))
             for entry in stale.read_cards(core.root, session)
             if entry.get("status", "open") == "open"
             and not (args.incomplete and stale.card_complete(entry))]
    if args.as_json:
        emit({"cards": [{**entry, "session": session, "missing": stale.card_missing(entry)}
                        for session, entry in found]}, True)
        return 0
    if not found:
        print("plumb: no open stale cards" + (" lacking anything" if args.incomplete else ""))
        return 0
    for session, entry in found:
        head = f"plumb: {entry.get('link')} (session {session})"
        if missing := stale.card_missing(entry):
            head += " lacks: " + "; ".join(missing)
        print(head)
        if args.incomplete:
            print(f"  complete it: plumb stale card {entry.get('link')} --session "
                  f"{session} --consequences \"...\" --why \"...\"")
            continue
        print(entry.get("topic") or "")
        if entry.get("why"):
            print(entry["why"])
        first = int(entry.get("recommended") or 0)
        said = list(entry.get("consequences") or ())
        for n, i in enumerate(sorted(range(len(entry.get("options") or ())),
                                     key=lambda i: i != first), start=1):
            print(f"  {n}. {entry['options'][i]}" + (" (recommended)" if i == first else "")
                  + (f" - {said[i]}" if i < len(said) and said[i] else ""))
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


def cmd_gone(command: str, argv: list[str]) -> int:
    """``approve``, ``revoke`` and ``relay``: refused, always, whoever runs them and whatever
    stdin holds (SR-210). The judge approves on the owner's behalf; no approval command exists."""
    del argv
    print(f"plumb: {command} no longer exists; nothing was recorded", file=sys.stderr)
    return EXIT_REFUSED


def cmd_validate(command: str, argv: list[str]) -> int:
    from plumb.merge import merge_check
    from plumb.validate import report

    parser = _parser(command, "Check records, links, logs and approvals. --merge BASE also "
                     "runs the merge-boundary checks (exit 4: waits on a judge or your answer).")
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
    from plumb.present.cards import awaiting_lines, judge_lines
    from plumb.query import retired_ids

    index = core.index()
    retired = retired_ids(index)   # SR-233: a retired record counts nowhere
    index = {i: r for i, r in index.items() if i not in retired}
    statuses = {i: s for i, s in core.status().items() if i not in retired}
    records = dict.fromkeys(KIND_PREFIX, 0)
    for record in index.values():
        records[record.kind] += 1
    requirements = [s for i, s in statuses.items() if index[i].kind == "requirement"]
    confirmation = {"proposed": 0, "confirmed": 0, "unconfirmed-edit": 0}
    for status in statuses.values():
        confirmation[status.confirmation] += 1
    links = {"current": 0, "stale": 0, "dangling": 0, "unpinned": 0, "retired": 0}
    for status in statuses.values():
        for state in status.links:
            links[state.state] += 1
    failing = {i: v for i, v in acceptance_failures(core).items() if i not in retired}
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
        "awaits_you": awaiting_lines(core, statuses),
        "judge_approved": judge_lines(core, statuses),
        "changed_tests": {i: list(s.changed_tests) for i, s in sorted(statuses.items())
                          if s.changed_tests},
        "verification": verification_state(core),
        "auto_approve": auto_approve_line(core),
    }


def auto_approve_line(core, *, quiet: bool = False) -> str | None:
    """Whether automatic confirmation is on and where that setting comes from: the owner's
    terminal or their typed /plumb auto-approve (SR-115, DEC-016). ``quiet``: None while it
    is off as it always was (never switched, no config.yaml on). Advisory: None on failure."""
    try:
        if quiet:                         # known without the judgment modules
            from plumb.capture.ownerconfig import latest

            if latest(core.events()) is None and not core.config.auto_approve.enabled:
                return None
        from plumb.capture.autoapprove import auto_approve_state, state_line

        return state_line(auto_approve_state(core))
    except Exception:  # noqa: BLE001 - a status line never fails the command
        return None


def _awareness_section(args: argparse.Namespace) -> list[str]:
    """sp6 9.4 (SR-078): every record other worktrees and branches are changing, with the
    worktree paths, and other branches' intent in flight."""
    try:
        from plumb.awareness.lines import status_section

        return status_section(_core(args))
    except Exception:  # noqa: BLE001 - awareness is advisory
        return []


def cmd_status(command: str, argv: list[str]) -> int:
    parser = _parser(command, "Counts, drift, what awaits you and the judge's approvals.")
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
        *data["awaits_you"],
    ]
    if data["judge_approved"]:
        lines += ["judge-approved:", *data["judge_approved"]]
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
    if data["auto_approve"]:
        lines.append(data["auto_approve"])
    lines += _awareness_section(args)
    from plumb.landing import board_lines

    lines += board_lines(Path(core.root))
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
    "unlink": cmd_unlink,
    "relink": cmd_relink,
    "repin": cmd_repin,
    "stale": cmd_stale,
    "approve": cmd_gone,
    "confirm": cmd_gone,
    "relay": cmd_gone,
    "revoke": cmd_gone,
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
