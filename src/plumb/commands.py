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


def _not_built(command: str, argv: list[str]) -> int:
    print(f"plumb: '{command}' is not available in this build", file=sys.stderr)
    return EXIT_USAGE


HANDLERS: dict[str, Callable[[str, list[str]], int]] = {
    "init": cmd_init,
}


def run(command: str, argv: list[str]) -> int:
    handler = HANDLERS.get(command, _not_built)
    try:
        return handler(command, argv)
    except SystemExit as exc:  # argparse usage errors and --help
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE
