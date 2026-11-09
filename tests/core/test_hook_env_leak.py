"""report-2680054f: git run for a scratch repository never reaches the host repository, even
when the hook that started plumb exported the host's GIT_DIR."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from plumb.background import GIT_HOOK_VARS, child_env, popen_options
from plumb.evaluate.run import _git
from tests.conftest import git


@pytest.fixture
def host(tmp_path: Path) -> tuple[Path, Path]:
    """A host repository with one worktree; returns (host, the worktree's git dir)."""
    root = tmp_path / "host"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.fileMode", "false")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
        "-m", "a")
    git(root, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "w")
    gitdir = git(tmp_path / "wt", "rev-parse", "--absolute-git-dir").strip()
    return root, Path(gitdir)


def _config(root: Path) -> tuple[str, str]:
    return (git(root, "config", "--local", "core.bare").strip(),
            git(root, "config", "--local", "core.fileMode").strip())


def test_the_test_run_starts_without_the_hook_variables() -> None:
    assert not set(GIT_HOOK_VARS) & set(os.environ)


def test_a_background_git_init_leaves_the_host_config_alone(
        host: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, gitdir = host
    monkeypatch.setenv("GIT_DIR", str(gitdir))   # what a post-commit hook in the worktree sets
    monkeypatch.setenv("GIT_INDEX_FILE", str(gitdir / "index"))
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert "GIT_DIR" not in child_env() and "GIT_INDEX_FILE" not in child_env()
    options = popen_options(scratch, drop=("PLUMB_JOB",))
    assert "GIT_DIR" not in options["env"]
    subprocess.Popen(["git", "init", "-q"], **options).wait(timeout=30)
    assert (scratch / ".git").is_dir()
    assert _config(root) == ("false", "false")


def test_the_evaluators_scratch_repository_is_its_own(
        host: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, gitdir = host
    monkeypatch.setenv("GIT_DIR", str(gitdir))
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _git(scratch, "init", "-q", "-b", "main")
    assert (scratch / ".git").is_dir()
    assert _config(root) == ("false", "false")
