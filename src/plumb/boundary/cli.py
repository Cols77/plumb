"""``plumb merge-check [BASE] [--run | --no-run] [--json] [--hook pre-push]`` and
``plumb merge-check --install-pre-push | --uninstall-pre-push`` (sp3, SR-047 to SR-052)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


STEP_CHECK = "checking the merge"       # SR-108
MERGE_END = "merge check finished"


def _head_is(git: Path, branch: str) -> bool:
    try:
        return (git / "HEAD").read_text(encoding="utf-8").strip() == "ref: refs/heads/" + branch
    except OSError:
        return False


def branch_gone(root: Path, branch: str) -> bool:
    """Whether ``branch`` has neither a ref file nor a packed-refs line (files only, no git
    process). A worktree's ``.git`` file leads to its git dir, whose ``commondir`` holds refs.
    The branch HEAD points at is never gone (an unborn branch has no ref yet), and a
    repository using reftable keeps no ref files to look in."""
    git = root / ".git"
    try:
        if git.is_file():
            git = (root / git.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
            if _head_is(git, branch):
                return False
            common = git / "commondir"
            if common.is_file():
                git = (git / common.read_text(encoding="utf-8").strip()).resolve()
        if not git.is_dir() or _head_is(git, branch) or (git / "reftable").is_dir():
            return False
        if (git / "refs" / "heads" / branch).is_file():
            return False
        packed = git / "packed-refs"
        return not (packed.is_file() and any(
            line.rstrip().endswith(" refs/heads/" + branch)
            for line in packed.read_text(encoding="utf-8").splitlines()))
    except (OSError, IndexError):
        return False


def detected_base(root: Path) -> str:
    """The repository's default branch when the config does not name it: where
    ``origin/HEAD`` points, else ``main`` if it exists, else ``master`` (files only, no git
    process: the post-edit hook asks on every edit)."""
    git = Path(root) / ".git"
    try:
        if git.is_file():                        # a worktree: its refs live in the main git dir
            git = (Path(root) / git.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
            common = git / "commondir"
            if common.is_file():
                git = (git / common.read_text(encoding="utf-8").strip()).resolve()
        head = (git / "refs" / "remotes" / "origin" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: refs/remotes/origin/"):
            return head.removeprefix("ref: refs/remotes/origin/")
    except (OSError, IndexError):
        pass
    root = Path(root)
    return "master" if branch_gone(root, "main") and not branch_gone(root, "master") else "main"


def merge_settings(core: Any) -> dict[str, Any]:
    """``merge.default_base`` (the detected default branch when unset) and
    ``merge.prepush_run_full`` (true), from the config (``MergeConfig``; a fake without the
    section gets the defaults)."""
    out = _configured(core)
    out["default_base"] = out["default_base"] or detected_base(Path(core.root))
    return out


def _configured(core: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"default_base": None, "prepush_run_full": True}
    section = getattr(core.config, "merge", None)
    for key in out:
        value = getattr(section, key, None)
        if value is None and isinstance(section, Mapping):
            value = section.get(key)
        if value is not None:
            out[key] = value
    return out


def _print_report(core: Any, base: str, *, run_full: bool, as_json: bool,
                  hook: bool = False) -> Any:
    """Compute, print and return one ``MergeReport`` (``hook``: inside the pre-push hook)."""
    import contextlib

    from plumb import progress
    from plumb.boundary import as_dict, merge_report
    from plumb.heavy import heavy
    from plumb.cliutil import emit

    with progress.scope(core.root, "merge-check") as reporter:
        reporter.update(STEP_CHECK)
        with (heavy(core.root, "plumb merge-check --run") if run_full
              else contextlib.nullcontext()):
            report = merge_report(core, base, run_full=run_full, hook=hook)
        reporter.done(MERGE_END)
    if as_json:
        emit(as_dict(report), True)
    else:  # SR-374 EX-6: only what holds the merge; plumb context merge prints it all
        from plumb.present import insights

        for line in insights.lines("merge", core, {"report": report}):
            print(line.text)
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
        LAND_HOOK,
        POST_HOOK,
        default_branch_of,
        ff_release,
        hook_line,
        install_commit_hook,
        install_hook,
        install_land_hook,
        install_post_hook,
        uninstall_hook,
    )
    from plumb.boundary.prepush import ForeignHookError
    from plumb.cliutil import emit
    from plumb.present import owner_text

    out: dict[str, Any] = {"hook": HOOK, "hooks": [HOOK, COMMIT_HOOK, POST_HOOK, LAND_HOOK]}
    lines: list[str] = []
    code = 0
    if args.install_pre_merge_commit:
        for hook, install, foreign in (
                (HOOK, install_hook, owner_text.FOREIGN_HOOK),
                (COMMIT_HOOK, install_commit_hook, owner_text.FOREIGN_COMMIT_HOOK),
                (POST_HOOK, install_post_hook, owner_text.FOREIGN_POST_HOOK),
                (LAND_HOOK, install_land_hook, owner_text.FOREIGN_LAND_HOOK)):
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
            removed = [hook for hook in (HOOK, COMMIT_HOOK, POST_HOOK, LAND_HOOK)
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
    parser.add_argument("--run", action="store_true",
                        help="run the full suite once when full verification is pending and "
                             "record the merge evidence on green (without it the check is "
                             "quick: it reads the recorded evidence and runs no test)")
    parser.add_argument("--hook", choices=["pre-push", "pre-merge-commit",
                                           "prepare-commit-msg", "post-merge", "post-commit"],
                        default=None,
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
    if args.hook == "post-commit":
        from plumb.boundary.premerge import run_post_commit

        return run_post_commit(root)
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
    # SR-260: by hand the check is the quick one; only the pre-push hook or --run runs tests
    run_full = args.run and not args.no_run
    return int(_print_report(core, base, run_full=run_full, as_json=args.as_json).exit)
