"""``plumb tests map|select|run`` and the aliases ``map`` and ``verify`` (spec 7, 9)."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from plumb.cliutil import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, add_common, emit, resolve_root


def _verify(args: argparse.Namespace) -> Any:
    from plumb.api import open_core
    from plumb.verify import open_verify

    return open_verify(open_core(resolve_root(args.root)))


def _parser(prog: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    add_common(parser)
    return parser


def cmd_map(prog: str, argv: list[str]) -> int:
    parser = _parser(prog, "Build the code-to-test map and write .plumb/test_map.txt.")
    parser.add_argument("--rebuild", action="store_true", help="ignore the parse cache")
    parser.add_argument("--coverage", action="store_true",
                        help="also record which functions each test executes (runs the tests "
                        "whose record is missing or stale, once, under coverage)")
    args = parser.parse_args(argv)
    from plumb.api import open_core
    from plumb.verify.testmap import build_map

    core = open_core(resolve_root(args.root))
    tmap = build_map(core, rebuild=args.rebuild)
    if args.coverage:
        return _map_coverage(core, args)
    if args.as_json:
        emit(tmap.as_dict(), True)
        return EXIT_OK
    data = tmap.as_dict()
    emit(f"plumb: test map: {len(tmap.test_files)} test files, {len(data['sources'])} "
         f"covered sources, {sum(1 for v in data['records'].values() if v)} requirements "
         "-> .plumb/test_map.txt (grep it)", False)
    return EXIT_OK


def _map_coverage(core: Any, args: argparse.Namespace) -> int:
    from plumb.verify import open_verify

    report = open_verify(core).map_coverage(rebuild=args.rebuild)
    if args.as_json:
        emit(report.as_dict(), True)
    else:
        lines = [f"plumb: function record: ran {len(report.ran)} tests, recorded "
                 f"{len(report.recorded)}, {report.fresh} already fresh"
                 + (f", {report.workers} workers" if report.workers else "")
                 + f" ({report.elapsed_s:g} s)"]
        if report.stats:
            lines.append("plumb: function record holds {tests} tests, {funcs} functions, "
                         "{hits} executions".format(**report.stats))
        lines += [f"plumb: {note}" for note in report.notes]
        lines += [f"plumb: not recorded (failed): {node}" for node in report.failed]
        emit(lines, False)
    return EXIT_FINDINGS if report.failed else EXIT_OK


def _selection_dict(sel: Any) -> dict[str, Any]:
    return {"changed": list(sel.changed), "nodes": list(sel.nodes), "reasons": dict(sel.reasons),
            "deferred": list(sel.deferred), "sampled": list(sel.sampled),
            "unknown_coverage": list(sel.unknown_coverage),
            "infra_changed": list(sel.infra_changed), "doc_only": sel.doc_only,
            "expected_s": sel.expected_s}


def cmd_select(prog: str, argv: list[str]) -> int:
    parser = _parser(prog, "The covering tests of changed paths, in priority order.")
    parser.add_argument("paths", nargs="*", help="changed paths (default: --changed)")
    parser.add_argument("--changed", action="store_true",
                        help="git status plus the session touched lists")
    parser.add_argument("--budget", type=float, default=None, help="turn budget in seconds")
    args = parser.parse_args(argv)
    verify = _verify(args)
    changed = args.paths if args.paths and not args.changed else verify.changed_paths()
    sel = verify.select(changed, budget_s=args.budget)
    if args.as_json:
        emit(_selection_dict(sel), True)
        return EXIT_OK
    lines = _selection_lines(sel)
    for node in sel.nodes:
        lines.append(f"  {node}  ({sel.reasons.get(node)})")
    emit(lines, False)
    return EXIT_OK


def _selection_lines(sel: Any) -> list[str]:
    if sel.doc_only:
        return ["plumb: documentation only: no covering tests to run"]
    lines = [f"plumb: covering tests {len(sel.nodes)} (expected {sel.expected_s:g} s)"
             + (f" | deferred {len(sel.deferred)} (budget)" if sel.deferred else "")]
    if sel.infra_changed:
        lines.append("plumb: full verification pending (shared test infrastructure changed: "
                     + ", ".join(sel.infra_changed) + ")")
    if sel.unknown_coverage:
        lines.append("plumb: unknown coverage for " + ", ".join(sel.unknown_coverage)
                     + f": sampled {len(sel.sampled)}; full verification pending")
    return lines


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def report_lines(report: Any) -> list[str]:
    from plumb.verify.policy import regression_instruction

    sel = report.selection
    if report.run_id is None:
        lines = (_selection_lines(sel) if sel is not None and sel.doc_only
                 else ["plumb: no covering tests to run"])
        if report.full_pending is not None and report.full_pending.pending:
            lines.append("plumb: full verification pending ("
                         + "; ".join(report.full_pending.reasons) + ")")
        return lines
    counts: dict[str, int] = {}
    for outcome in report.outcomes.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    regress = {r["node"] for r in report.regressions}
    parts = [f"{counts.get('passed', 0)} passed"]
    if counts.get("flaky"):
        parts.append(f"{counts['flaky']} flaky")
    failed = [n for n in report.failed if n not in regress and n not in report.not_yet_passing]
    if failed:
        parts.append(f"{len(failed)} failed")
    if report.regressions:
        parts.append(_plural(len(report.regressions), "regression"))
    if report.not_yet_passing:
        parts.append(f"{len(report.not_yet_passing)} not yet passing")
    skipped = counts.get("skipped", 0) + counts.get("xfailed", 0)
    if skipped:
        parts.append(f"{skipped} skipped")
    head = (f"plumb: ran {_plural(len(report.outcomes), 'test')} in {report.elapsed_s:g} s "
            f"(run {report.run_id}{', full' if report.full else ''}): " + ", ".join(parts))
    if sel is not None and sel.deferred:
        head += f" | deferred {len(sel.deferred)} (budget)"
    lines = [head]
    if report.timed_out:
        lines.append(f"plumb: timeout after {report.timeout_s:g} s: "
                     f"{len(report.outcomes)} finished and were recorded; the rest gives no "
                     "evidence (the next selection allows for this pace); run again, or "
                     "narrow it with --nodes")
    if report.aborted:
        lines.append(f"plumb: run aborted ({report.aborted}): the selected tests did not run "
                     "and count as failed; fix the cause and run again")
    if report.discarded:
        lines.append(f"plumb: run discarded ({report.discarded} during the run): no fresh "
                     "evidence; run it again")
    for path in report.collection_errors:
        lines.append(f"plumb: collection error: {path}")
    for reg in report.regressions:
        lines.append(regression_instruction(reg["node"], reg["passed_in"],
                                            reg["test_changed_since_pass"]))
    for node in report.not_yet_passing:
        lines.append(f"plumb: not yet passing: {node}")
    for node in failed:
        lines.append(f"plumb: failed: {node}")
    for node in report.flaky:
        lines.append(f"plumb: flaky (failed, then passed on a same-tree rerun): {node}")
    for node in report.removed_after_passing:
        lines.append(f"plumb: removed after passing: {node}")
    lines += [f"plumb: {note}" for note in report.notes]
    if sel is not None:
        lines += [line for line in _selection_lines(sel)[1:]]
    if report.full_pending is not None and report.full_pending.pending and not report.full:
        lines.append("plumb: full verification pending ("
                     + "; ".join(report.full_pending.reasons)
                     + "); satisfied by plumb tests run --full at the merge boundary")
    return lines


def cmd_run(prog: str, argv: list[str]) -> int:
    parser = _parser(prog, "Run covering tests (or the full suite) and record evidence.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--changed", action="store_true",
                       help="covering tests of git status plus the session touched lists "
                            "(default)")
    group.add_argument("--paths", nargs="+", metavar="P", help="covering tests of these paths")
    group.add_argument("--nodes", nargs="+", metavar="N", help="these test files or node ids")
    group.add_argument("--full", action="store_true",
                       help="the whole suite (owner request or merge boundary)")
    parser.add_argument("--budget", type=float, default=None, help="turn budget in seconds")
    args = parser.parse_args(argv)
    verify = _verify(args)
    report = verify.run(changed=args.paths, nodes=args.nodes, full=args.full,
                        budget_s=args.budget)
    if args.as_json:
        emit(report.as_dict(), True)
    else:
        emit(report_lines(report), False)
    if report.run_id is None:
        return EXIT_OK
    return EXIT_OK if report.ok else EXIT_FINDINGS


def cmd_impact(prog: str, argv: list[str]) -> int:
    parser = _parser(prog, "Downstream of a record or path: records and covering tests "
                     "with their evidence state.")
    parser.add_argument("ref", help="a record ID or a repository path")
    args = parser.parse_args(argv)
    data = _verify(args).impact(args.ref)
    if args.as_json:
        emit(data, True)
        return EXIT_OK
    lines = [f"plumb impact {data['ref']}",
             "records: " + (", ".join(data["records"]) or "none")]
    if data["paths"]:
        lines.append("code: " + ", ".join(data["paths"]))
    lines.append(f"tests ({len(data['tests'])}):")
    for test in data["tests"]:
        flag = "  regression" if test["regression"] else ""
        lines.append(f"  {test['test']}  {test['state']}{flag}")
    emit(lines, False)
    return EXIT_OK


def cmd_waive(prog: str, argv: list[str]) -> int:
    import re

    parser = _parser(prog, "Owner waiver pinned to a diff digest (owner only: a y/N in the "
                     "owner's interactive terminal; refused under the agent session marker).")
    parser.add_argument("--diff-digest", default=None,
                        help="sha256:<hex> (default: the digest of git diff HEAD)")
    parser.add_argument("--merge", metavar="BASE", default=None,
                        help="waive the merge boundary's full run for exactly the change "
                        "from the merge base of BASE (any later edit voids it)")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    from plumb.api import open_core
    from plumb.approvals import Declined
    from plumb.verify.policy import DIGEST_RE, WaiverRefused, current_diff_digest, waive

    core = open_core(resolve_root(args.root))
    digest = args.diff_digest
    if digest is not None and not re.match(DIGEST_RE, digest):
        print("plumb: --diff-digest must be sha256:<64 lowercase hex>", file=sys.stderr)
        return EXIT_USAGE
    if digest is not None and args.merge is not None:
        print("plumb: pass --diff-digest or --merge, not both", file=sys.stderr)
        return EXIT_USAGE
    try:
        if digest is None:
            from plumb.approvals import marker

            if marker():
                raise WaiverRefused("plumb tests waive refused: the agent session marker is "
                                    "set; only the owner waives, in their own terminal")
            if args.merge is not None:
                import subprocess

                from plumb.verify.policy import range_digest

                fork = subprocess.run(["git", "merge-base", args.merge, "HEAD"], cwd=core.root,
                                      capture_output=True, text=True)
                if fork.returncode != 0:
                    print(f"plumb: cannot find the merge base of {args.merge} and HEAD",
                          file=sys.stderr)
                    return EXIT_USAGE
                digest = range_digest(core.root, fork.stdout.strip())
            else:
                digest = current_diff_digest(core.root)
        entry = waive(core, digest, args.reason)
    except WaiverRefused as exc:
        print(f"plumb: refused: {exc}", file=sys.stderr)
        return 3
    except Declined as exc:
        print(f"{exc}")
        return EXIT_OK
    emit({"waiver": digest, "reason": args.reason, "digest": entry.digest} if args.as_json
         else f"plumb: waiver recorded for diff {digest}", args.as_json)
    return EXIT_OK


_TESTS_HELP = """usage: plumb tests {map,select,run} [options]

  map      build the code-to-test map; writes .plumb/test_map.txt (alias: plumb map)
  select   the covering tests of changed paths, in priority order
  run      run covering tests (--changed, --paths, --nodes) or --full; records evidence
           (alias: plumb verify)
  waive    owner waiver pinned to a diff digest (owner only)
"""


def run(command: str, argv: list[str]) -> int:
    if command == "map":
        return cmd_map("plumb map", argv)
    if command == "verify":
        return cmd_run("plumb verify", argv)
    if command == "impact":
        return cmd_impact("plumb impact", argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_TESTS_HELP)
        return EXIT_OK if argv else EXIT_USAGE
    sub, rest = argv[0], argv[1:]
    if sub == "map":
        return cmd_map("plumb tests map", rest)
    if sub == "select":
        return cmd_select("plumb tests select", rest)
    if sub == "run":
        return cmd_run("plumb tests run", rest)
    if sub == "waive":
        return cmd_waive("plumb tests waive", rest)
    print(f"plumb: unknown tests command '{sub}' (map, select, run)", file=sys.stderr)
    return EXIT_USAGE
