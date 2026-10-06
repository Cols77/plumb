"""Temporary git repositories, worktrees and commits for the LOGS lane's tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", check=check)


def make_repo(root: Path) -> Path:
    """A git repository on ``main`` adopted by plumb, with one commit."""
    from plumb.commands import init_repo

    root.mkdir(parents=True, exist_ok=True)
    run_git(root, "init", "-q", "-b", "main")
    run_git(root, "config", "user.email", "test@example.com")
    run_git(root, "config", "user.name", "Test")
    run_git(root, "config", "core.autocrlf", "false")
    init_repo(root)
    (root / "README.md").write_text("test repo\n", encoding="utf-8")
    commit_all(root, "initial")
    return root


def add_worktree(root: Path, path: Path, branch: str) -> Path:
    run_git(root, "worktree", "add", "-q", "-b", branch, str(path))
    return path


def commit_all(root: Path, message: str) -> str:
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "--no-verify", "-m", message)
    return run_git(root, "rev-parse", "HEAD").stdout.strip()
