"""``plumb merge-check [BASE] [--no-run] [--json] [--hook pre-push]`` and
``plumb merge-check --install-pre-push | --uninstall-pre-push`` (sp3, SR-047 to SR-052)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def merge_settings(core: Any) -> dict[str, Any]:
    """``merge.default_base`` (main) and ``merge.prepush_run_full`` (true), from the config
    when it carries the section, else read from ``.plumb/config.yaml`` directly."""
    out: dict[str, Any] = {"default_base": "main", "prepush_run_full": True}
    section = getattr(core.config, "merge", None)
    if section is not None:
        for key in out:
            value = getattr(section, key, None)
            if value is None and isinstance(section, Mapping):
                value = section.get(key)
            if value is not None:
                out[key] = value
        return out
    try:
        import yaml

        data = yaml.safe_load((Path(core.root) / ".plumb" / "config.yaml")
                              .read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, ImportError):
        return out
    merge = data.get("merge") if isinstance(data, Mapping) else None
    if isinstance(merge, Mapping):
        if isinstance(merge.get("default_base"), str) and merge["default_base"].strip():
            out["default_base"] = merge["default_base"].strip()
        if isinstance(merge.get("prepush_run_full"), bool):
            out["prepush_run_full"] = merge["prepush_run_full"]
    return out


def _print_report(core: Any, base: str, *, run_full: bool, as_json: bool,
                  hook: bool = False) -> Any:
    """Compute, print and return one ``MergeReport`` (``hook``: inside the pre-push hook)."""
    from plumb.boundary import as_dict, merge_report, render
    from plumb.cliutil import emit

    report = merge_report(core, base, run_full=run_full, hook=hook)
    if as_json:
        emit(as_dict(report), True)
    else:
        for line in render(report):
            print(line)
    return report


def _hook_pre_push(core: Any, run_full: bool) -> int:
    from plumb.boundary.prepush import hook_bases

    settings = merge_settings(core)
    bases = hook_bases(Path(core.root), sys.stdin.read().splitlines(),
                       str(settings["default_base"]))
    if not bases:
        print("plumb pre-push: no pushed ref is the checked-out HEAD with a known base; "
              "merge-check skipped")
        return 0
    worst = 0
    seen: set[str] = set()
    # One merge-check invocation starts at most ONE full-suite run, whatever its result
    # (sp3 4): once a report has run the suite, the remaining bases only report.
    may_run = run_full and bool(settings["prepush_run_full"])
    for ref, base in bases:
        if base in seen:
            continue
        seen.add(base)
        print(f"plumb pre-push: {ref}")
        report = _print_report(core, base, run_full=may_run, as_json=False, hook=True)
        if (report.full_run or {}).get("ran"):
            may_run = False
        worst = max(worst, report.exit)
    if worst:
        print(f"plumb pre-push: the push is refused (merge-check exit {worst}); fix the report "
              "above, or push with --no-verify to bypass the hook", file=sys.stderr)
    return worst


def _premerge_install(root: Path, args: Any) -> int:
    """``--install-pre-merge-commit`` / ``--uninstall-pre-merge-commit`` (sp6 10): the quick
    merge check's two hooks, pre-merge-commit and prepare-commit-msg (``premerge``)."""
    from plumb.boundary.premerge import (
        COMMIT_HOOK,
        HOOK,
        POST_HOOK,
        default_branch_of,
        ff_release,
        hook_line,
        install_commit_hook,
        install_hook,
        install_post_hook,
        uninstall_hook,
    )
    from plumb.boundary.prepush import ForeignHookError
    from plumb.cliutil import emit
    from plumb.present import owner_text

    out: dict[str, Any] = {"hook": HOOK, "hooks": [HOOK, COMMIT_HOOK, POST_HOOK]}
    lines: list[str] = []
    code = 0
    if args.install_pre_merge_commit:
        for hook, install, foreign in (
                (HOOK, install_hook, owner_text.FOREIGN_HOOK),
                (COMMIT_HOOK, install_commit_hook, owner_text.FOREIGN_COMMIT_HOOK),
                (POST_HOOK, install_post_hook, owner_text.FOREIGN_POST_HOOK)):
            try:
                out.setdefault("paths", {})[hook] = str(install(root, args.interpreter))
            except ForeignHookError:
                out["foreign"] = True
                out.setdefault("foreign_hooks", []).append(hook)
                out.setdefault("hook_lines", {})[hook] = hook_line(args.interpreter, hook)
                lines.append(foreign)
                code = 1
            except (OSError, subprocess.CalledProcessError) as exc:
                out.setdefault("errors", {})[hook] = str(exc)
                lines.append(f"plumb: the merge check was not changed: {exc}")
                code = 1
        out["installed"] = code == 0
        if HOOK in out.get("paths", {}):
            out["path"] = out["paths"][HOOK]
        if HOOK in out.get("hook_lines", {}):
            out["hook_line"] = out["hook_lines"][HOOK]
        if code == 0:
            lines.append(owner_text.PREMERGE_INSTALLED)
    else:
        try:
            removed = [hook for hook in (HOOK, COMMIT_HOOK, POST_HOOK)
                       if uninstall_hook(root, hook)]
            if ff_release(root):
                lines.append(owner_text.FF_HOLD_REMOVED.format(branch=default_branch_of(root)))
        except (OSError, subprocess.CalledProcessError) as exc:
            removed, code = [], 1
            out["error"] = str(exc)
            lines.append(f"plumb: the merge check was not changed: {exc}")
        out["removed"] = bool(removed)
        if not code:
            lines.append(owner_text.PREMERGE_REMOVED if removed else (
                "plumb: no merge check of plumb's to remove (your own hook is left)"))
    out["line"] = "\n".join(lines)
    if args.as_json:
        emit(out, True)
    else:
        for line in lines:
            print(line)
    return code


def run(command: str, argv: list[str]) -> int:
    import argparse

    from plumb.api import open_core
    from plumb.boundary.prepush import ForeignHookError
    from plumb.cliutil import add_common, resolve_root

    parser = argparse.ArgumentParser(
        prog="plumb merge-check",
        description="The merge boundary: every touched requirement confirmed, approvals for "
                    "a glance, one full-suite run when needed, claims, links and log "
                    "integrity. Exit 0 green, 1 integrity/claims/links, 4 waits for the "
                    "owner's confirmation, 5 verification holds the merge.")
    parser.add_argument("base", nargs="?", default=None,
                        help="the branch or commit the change merges into (default: "
                             "merge.default_base, main)")
    parser.add_argument("--no-run", action="store_true",
                        help="never run the full suite; report what would hold")
    parser.add_argument("--hook", choices=["pre-push", "pre-merge-commit",
                                           "prepare-commit-msg", "post-merge"], default=None,
                        help="git hook mode: pre-push reads the pushed refs on stdin; "
                             "pre-merge-commit is the quick check of the merge in progress "
                             "(no test run, R17); prepare-commit-msg the same check of a "
                             "merge finished by hand and of each rebase, cherry-pick or "
                             "revert step; post-merge the same check after git fast-forwarded "
                             "the default branch, which it puts back when the check holds")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install-pre-push", action="store_true",
                       help="write the git pre-push hook running this check (init and hooks "
                       "install write it by default)")
    group.add_argument("--uninstall-pre-push", action="store_true",
                       help="remove plumb's pre-push hook (a foreign hook is left)")
    group.add_argument("--install-pre-merge-commit", action="store_true",
                       help="write the git pre-merge-commit and prepare-commit-msg hooks "
                            "(the quick merge check; plumb hooks install writes them by "
                            "default)")
    group.add_argument("--uninstall-pre-merge-commit", action="store_true",
                       help="remove plumb's pre-merge-commit and prepare-commit-msg hooks "
                            "(a foreign hook is left)")
    parser.add_argument("--interpreter", default=sys.executable,
                        help="Python that runs the pre-push hook (default: this one)")
    add_common(parser)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    root = resolve_root(args.root)
    if args.install_pre_merge_commit or args.uninstall_pre_merge_commit:
        return _premerge_install(root, args)
    if args.install_pre_push or args.uninstall_pre_push:
        from plumb.boundary.prepush import install_pre_push_hook, uninstall_pre_push_hook

        try:
            if args.install_pre_push:
                path = install_pre_push_hook(root, args.interpreter)
                print(f"plumb: pre-push hook installed ({path}); git push now runs "
                      "plumb merge-check")
            elif uninstall_pre_push_hook(root):
                print("plumb: pre-push hook removed")
            else:
                print("plumb: no plumb pre-push hook to remove (a foreign hook is left)")
        except ForeignHookError as exc:
            print(f"plumb: {exc}", file=sys.stderr)
            return 1
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"plumb: pre-push hook not changed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.hook == "post-merge":
        from plumb.boundary.premerge import run_post_merge

        return run_post_merge(root)
    if args.hook == "prepare-commit-msg":
        from plumb.boundary.premerge import commit_hook_skips

        if commit_hook_skips(root):
            return 0
    core = open_core(root)
    if args.hook in ("pre-merge-commit", "prepare-commit-msg"):
        from plumb.boundary.premerge import run_hook

        return run_hook(core, args.hook)
    if args.hook == "pre-push":
        return _hook_pre_push(core, not args.no_run)
    base = args.base or str(merge_settings(core)["default_base"])
    return int(_print_report(core, base, run_full=not args.no_run, as_json=args.as_json).exit)
