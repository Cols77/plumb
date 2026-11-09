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


class _Done:
    """What a finished pytest process looks like to ``run_pytest``."""

    returncode = 0

    def communicate(self, timeout: float | None = None) -> tuple[bytes, None]:
        return b"", None

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


def test_the_full_run_starts_pytest_without_the_hook_variables(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-push hook runs the suite inside the hook process: its pytest must not inherit
    the hook's GIT_DIR, or every fixture's ``git init`` reinitialises the host repository."""
    from plumb.verify import runner

    monkeypatch.setenv("GIT_DIR", str(tmp_path / "host" / ".git" / "worktrees" / "wt"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "index"))
    seen: dict[str, str] = {}

    def popen(cmd: list[str], **kwargs: object) -> _Done:
        seen.update(kwargs["env"])   # type: ignore[call-overload]
        return _Done()

    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    runner.run_pytest(tmp_path, ["tests"])
    assert seen and "PLUMB_REPORT" in seen
    assert not set(GIT_HOOK_VARS) & set(seen)


def test_the_fix_jobs_pytest_runs_without_the_hook_variables(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import contextlib
    from types import SimpleNamespace

    import plumb.links
    from plumb import selfdebug

    monkeypatch.setenv("GIT_DIR", str(tmp_path / "host" / ".git" / "worktrees" / "wt"))
    seen: dict[str, str] = {}

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs["env"])   # type: ignore[call-overload]
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(selfdebug.subprocess, "run", run)
    monkeypatch.setattr(selfdebug, "heavy", lambda cwd, what: contextlib.nullcontext())
    monkeypatch.setattr(plumb.links, "default_runner", lambda core: lambda paths: (True, ""))
    ok, _ = selfdebug._runner(SimpleNamespace(root=tmp_path))(["tests/test_a.py::test_b"])
    assert ok and seen["PYTHONPATH"] == str(tmp_path / "src")
    assert not set(GIT_HOOK_VARS) & set(seen)


def test_the_evaluators_agent_runs_without_the_hook_variables(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent's own git commands in the scratch folder stay in the scratch folder."""
    from plumb.evaluate import run as runmod

    monkeypatch.setenv("GIT_DIR", str(tmp_path / "host" / ".git"))
    seen: dict[str, str] = {}

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs["env"])   # type: ignore[call-overload]
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    monkeypatch.setattr(runmod.subprocess, "run", run)
    for env in (None, dict(os.environ)):   # evaluate passes none, proofcheck its own copy
        seen.clear()
        runmod._claude_call("claude", tmp_path, "hi", model="sonnet", session_id=None,
                            system="", timeout_s=1, env=env, max_turns=1, extra=[], tools=[])
        assert seen and "PATH" in seen
        assert not set(GIT_HOOK_VARS) & set(seen)
