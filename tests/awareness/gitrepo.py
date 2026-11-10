"""Temporary git repositories and worktrees for the AWARENESS lane's tests.

The phase-0 ``tests/gitrepo.py`` was not on ``main`` when this lane started; these helpers
are the lane's own (sp6 plan 2) and never touch the iaso repository itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

KIND_DIRS = {"INT": "intents", "SR": "requirements", "DEC": "decisions", "FEAT": "features",
             "NC": "ncs"}


def run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def make_repo(path: Path) -> Path:
    """A git repository adopted by iaso, with one commit on ``main``."""
    from iaso.commands import init_repo

    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-q", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    run_git(path, "config", "core.autocrlf", "false")
    init_repo(path)
    (path / "README.md").write_text("test repo\n", encoding="utf-8")
    commit_all(path, "initial")
    return path


def commit_all(root: Path, message: str) -> str:
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "--no-verify", "-m", message)
    return run_git(root, "rev-parse", "HEAD").strip()


def add_worktree(root: Path, path: Path, branch: str) -> Path:
    run_git(root, "worktree", "add", "-q", "-b", branch, str(path))
    return path


def write_record(root: Path, record_id: str, title: str, **fields: object) -> Path:
    """A minimal record file (frontmatter only)."""
    import yaml

    data = {"id": record_id, "title": title, **fields}
    path = root / ".iaso" / KIND_DIRS[record_id.split("-")[0]] / f"{record_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
                      + "---\n").encode("utf-8"))
    return path


def requirement(root: Path, record_id: str, title: str, statement: str = "",
                feature: str | None = None) -> Path:
    fields: dict[str, object] = {"statement": statement or title}
    if feature:
        fields["feature"] = feature
    return write_record(root, record_id, title, **fields)


def listing(root: Path) -> dict[str, tuple[int, float]]:
    """Every file under ``root`` (``.git`` content included) with its size and mtime."""
    out: dict[str, tuple[int, float]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime)
    return out
