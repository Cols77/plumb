"""The working tree's leftovers, told once when a session starts (INT-027, SR-009).

At the start of a session nothing in the tree was made by it, so an unfinished merge, rebase
or cherry-pick, staged changes and modified tracked files are work from before. One
``git status --porcelain=v2`` call, started beside the brief's own reading so it costs no
extra wall time; a git that is slow, missing or failing says nothing (never a blocked start).
Untracked files are not counted: they are not work in progress, and plumb's own logs are
among them.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

GIT_TIMEOUT_S = 0.8
_OPERATIONS = (("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
               ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert"),
               ("MERGE_HEAD", "merge"))


def git_dir(root: Path) -> Path | None:
    """The repository's git directory: ``.git`` itself, or where a worktree's ``.git`` file
    points."""
    dot = Path(root) / ".git"
    if dot.is_dir():
        return dot
    try:
        text = dot.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    target = Path(text.split(":", 1)[1].strip())
    return target if target.is_absolute() else Path(root) / target


def unfinished_operation(root: Path) -> str | None:
    """``merge``, ``rebase``, ``cherry-pick`` or ``revert`` when one was left unfinished."""
    directory = git_dir(root)
    if directory is None:
        return None
    for name, word in _OPERATIONS:
        if (directory / name).exists():
            if name == "rebase-apply" and (directory / name / "applying").exists():
                continue  # a mailbox patch series, not a rebase
            return word
    return None


def count_changes(porcelain: str) -> tuple[int, int, int]:
    """(files in conflict, files staged, tracked files modified) from ``--porcelain=v2``."""
    conflict = staged = modified = 0
    for line in porcelain.splitlines():
        if line.startswith("u "):
            conflict += 1
        elif line.startswith(("1 ", "2 ")):
            status = line[2:4]
            staged += status[0] != "."
            modified += status[1] != "."
    return conflict, staged, modified


def _files(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def describe(operation: str | None, counts: tuple[int, int, int]) -> str | None:
    """The one owner-level line, or None when the tree holds nothing from before."""
    conflict, staged, modified = counts
    parts = [f"{_files(n)} {what}" for n, what in
             ((conflict, "in conflict"), (staged, "staged"), (modified, "modified")) if n]
    if operation is None and not parts:
        return None
    tail = ", ".join(parts)
    if operation is not None:
        head = f"An earlier {operation} was left unfinished"
        return f"plumb: {head}: {tail} (from before this session)" if tail \
            else f"plumb: {head} (from before this session)"
    return f"plumb: The working tree holds work from before this session: {tail}"


class TreeScan:
    """``git status`` running while the brief is read; ``line`` collects the answer."""

    def __init__(self, root: Path, timeout: float = GIT_TIMEOUT_S) -> None:
        self.root = Path(root)
        self.timeout = timeout
        self.output: str | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain=v2", "--untracked-files=no"], cwd=self.root,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.timeout, check=False)
        except (OSError, subprocess.SubprocessError):
            return  # git missing or slow: no word about the tree rather than a late start
        if result.returncode == 0:
            self.output = result.stdout

    def line(self, wait_s: float) -> str | None:
        self._thread.join(max(wait_s, 0.0))
        if self.output is None:
            return None
        try:
            return describe(unfinished_operation(self.root), count_changes(self.output))
        except Exception:  # noqa: BLE001 - a notice never fails the start
            return None
