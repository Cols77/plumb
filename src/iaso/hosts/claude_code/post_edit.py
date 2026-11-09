"""PostToolUse on Edit, Write, MultiEdit and NotebookEdit: edit tracking (spec 6.3).

Appends the edited file's repository-relative path to
``.iaso/session/<session_id>/touched.txt``, and to this worktree's
``.iaso/cache/changing.json`` (``iaso.awareness.publish.note_edit``, sp6 9.2), so a
session in another worktree hears of the edit before the turn ends. Standard library only:
no YAML, no record index. Registered with ``"async": true`` so it adds no blocking latency.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import TextIO

from iaso.hosts.claude_code.hookio import HookContext, HookOutput, run_hook

BUDGET_MS = 300


def repo_relative(root: Path, raw: str, cwd: str | None = None) -> str | None:
    """``raw`` as a repository-relative POSIX path, or None when it is outside ``root``."""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        base = Path(cwd) if cwd and Path(cwd).is_absolute() else root
        path = base / path
    try:
        resolved = Path(os.path.normpath(path.resolve(strict=False)))
        rel = resolved.relative_to(Path(os.path.normpath(root.resolve())))
    except (OSError, ValueError):
        return None
    text = PurePosixPath(*rel.parts).as_posix() if rel.parts else ""
    if not text or text == "." or text.startswith(".."):
        return None
    return text


def handle(ctx: HookContext) -> HookOutput | None:
    tool_input = ctx.data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str):
        return None
    cwd = ctx.data.get("cwd")
    rel = repo_relative(ctx.root, raw, cwd if isinstance(cwd, str) else None)
    if rel is None:
        return None
    directory = ctx.session_dir / ctx.session_id
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "touched.txt").open("a", encoding="utf-8", newline="\n") as handle_:
        handle_.write(rel + "\n")
    try:  # sp6 9.2: another worktree's session sees the edit before this turn ends
        from iaso.awareness.publish import note_edit

        note_edit(ctx.root, rel)
    except Exception:  # noqa: BLE001 - awareness never fails the hook
        pass
    return None


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("post-edit", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=BUDGET_MS, json_output=True, watchdog=watchdog, start=start)
