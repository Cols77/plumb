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


def _print_report(core: Any, base: str, *, run_full: bool, as_json: bool) -> int:
    from plumb.boundary import as_dict, merge_report, render
    from plumb.cliutil import emit

    report = merge_report(core, base, run_full=run_full)
    if as_json:
        emit(as_dict(report), True)
    else:
        for line in render(report):
            print(line)
    return report.exit


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
    for ref, base in bases:
        if base in seen:
            continue
        seen.add(base)
        print(f"plumb pre-push: {ref}")
        code = _print_report(core, base, run_full=run_full and bool(settings["prepush_run_full"]),
                             as_json=False)
        worst = max(worst, code)
    if worst:
        print(f"plumb pre-push: the push is refused (merge-check exit {worst}); fix the report "
              "above, or push with --no-verify to bypass the hook", file=sys.stderr)
    return worst


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
    parser.add_argument("--hook", choices=["pre-push"], default=None,
                        help="git hook mode: read the pushed refs on stdin")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install-pre-push", action="store_true",
                       help="write the optional git pre-push hook running this check")
    group.add_argument("--uninstall-pre-push", action="store_true",
                       help="remove plumb's pre-push hook (a foreign hook is left)")
    parser.add_argument("--interpreter", default=sys.executable,
                        help="Python that runs the pre-push hook (default: this one)")
    add_common(parser)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    root = resolve_root(args.root)
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
    core = open_core(root)
    if args.hook == "pre-push":
        return _hook_pre_push(core, not args.no_run)
    base = args.base or str(merge_settings(core)["default_base"])
    return _print_report(core, base, run_full=not args.no_run, as_json=args.as_json)
