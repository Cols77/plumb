"""Silence when not adopted (SP7 4.3 check 1; SR-083 EX-3, EX-4): in a repository without
iaso's record folder the plugin's only output is one line at a session's start, and no hook
starts Python."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from iaso.present import owner_text

from .helpers import (
    SH,
    env_with,
    git_repo,
    hook_data,
    needs_sh,
    ready_home,
    run_hook,
    sentinel_bin,
)

pytestmark = [needs_sh, pytest.mark.sr("SR-280")]
HINT = {"systemMessage": owner_text.NOT_ADOPTED}


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    """A git repository iaso has not adopted, iaso's environment ready (so only the walk
    keeps Python from starting), and every interpreter a sentinel."""
    sentinel = tmp_path / "sentinel.txt"
    poison = sentinel_bin(tmp_path / "poison", sentinel)
    home = ready_home(tmp_path / "home", poison / "python")
    root = git_repo(tmp_path / "repo")
    env = env_with([poison], IASO_HOME=str(home), CLAUDE_PROJECT_DIR=str(root))
    return root, env, sentinel


def test_only_hint_at_startup(setup: tuple[Path, dict[str, str], Path]) -> None:
    root, env, sentinel = setup
    for source in ("startup", "resume"):
        result = run_hook("session-start", root, hook_data("session-start", source=source), env)
        assert result.returncode == 0
        assert json.loads(result.stdout) == HINT
    for source in ("clear", "compact"):
        result = run_hook("session-start", root, hook_data("session-start", source=source), env)
        assert (result.returncode, result.stdout) == (0, "")
    assert not sentinel.exists()
    assert not (root / ".iaso").exists() and not (root / ".iaso").exists()


@pytest.mark.parametrize("event", ["prompt", "pre-tool", "post-edit", "stop"])
def test_silent(setup: tuple[Path, dict[str, str], Path], event: str) -> None:
    root, env, sentinel = setup
    data = hook_data(event)
    if event == "pre-tool":  # even a call naming iaso: nothing to guard here
        data["tool_input"] = {"command": "iaso approve SR-001"}
    result = run_hook(event, root, data, env)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not sentinel.exists()
    assert not (root / ".iaso").exists() and not (root / ".iaso").exists()


def test_not_a_git_work_tree_is_silent(tmp_path: Path) -> None:
    folder = tmp_path / "loose"
    folder.mkdir()
    env = env_with([], IASO_HOME=str(tmp_path / "home"), CLAUDE_PROJECT_DIR=str(folder))
    result = run_hook("session-start", folder, hook_data("session-start"), env)
    assert (result.returncode, result.stdout) == (0, "")


def _best(argv: list[str], cwd: Path, env: dict[str, str], data: str, runs: int = 7) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run(argv, input=data, cwd=cwd, env=env, capture_output=True, text=True,
                       timeout=30)
        best = min(best, time.perf_counter() - start)
    return best


def test_no_python_started(setup: tuple[Path, dict[str, str], Path]) -> None:
    """Each hook's own work stays within a tenth of a second (SR-083 EX-4): measured against
    starting the shell alone, which is the host's cost, not iaso's."""
    from .helpers import HOOK, slashes

    root, env, sentinel = setup
    assert SH is not None
    for event in ("session-start", "prompt", "pre-tool", "post-edit", "stop"):
        data = json.dumps(hook_data(event))
        for attempt in range(5):  # a loaded machine skews one sample; re-measure both sides
            bare = _best([SH, "-c", "exit 0"], root, env, "")
            took = _best([SH, slashes(HOOK), event], root, env, data)
            if took - bare < 0.1:
                break
            time.sleep(2)
        assert took - bare < 0.1, (event, took, bare)
    assert not sentinel.exists()


def test_ignored_repo_silent(setup: tuple[Path, dict[str, str], Path],
                             monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.plugin import cli

    root, env, sentinel = setup
    monkeypatch.setenv("IASO_HOME", env["IASO_HOME"])
    cli.ignore(root)
    for start in (str(root), None):  # the project folder as Claude Code names it, or the cwd
        run_env = dict(env)
        if start is None:
            run_env.pop("CLAUDE_PROJECT_DIR")
        result = run_hook("session-start", root, hook_data("session-start"), run_env)
        assert (result.returncode, result.stdout) == (0, "")
    cli.unignore(root)
    result = run_hook("session-start", root, hook_data("session-start"), env)
    assert json.loads(result.stdout) == HINT
    assert not sentinel.exists()


def test_a_folder_under_iasos_own_home_is_not_adopted(tmp_path: Path) -> None:
    """~/.iaso is iaso's home (env/), not a repository's records, even when a folder named
    records were once written there: a folder under the user's home stays silent."""
    home = tmp_path / "user"
    (home / ".iaso" / "env").mkdir(parents=True)
    (home / ".iaso" / "requirements").mkdir()
    (home / ".iaso" / "config.yaml").write_text("{}\n", encoding="utf-8")
    folder = home / "loose"
    folder.mkdir()
    env = env_with([], IASO_HOME=str(home / ".iaso"), CLAUDE_PROJECT_DIR=str(folder))
    result = run_hook("session-start", folder, hook_data("session-start"), env)
    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.sr("SR-202")
def test_init_hint_puts_iaso_on_the_agents_path(setup: tuple[Path, dict[str, str], Path],
                                                 tmp_path: Path) -> None:
    """SR-122 EX-2: where the session start suggests /iaso init, the agent's shell gets the
    plugin's bin/ on its PATH, so the `iaso init` the command runs resolves; once only."""
    root, env, sentinel = setup
    env_file = tmp_path / "claude-env.sh"
    env_file.write_text("", encoding="utf-8")
    run_env = dict(env, CLAUDE_ENV_FILE=str(env_file))
    for _ in range(2):
        result = run_hook("session-start", root, hook_data("session-start"), run_env)
        assert json.loads(result.stdout) == HINT
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines.count("export IASO_AGENT_SESSION=claude-code") == 1
    path_lines = [line for line in lines if line.startswith("export PATH=")]
    assert len(path_lines) == 1 and "/bin:$PATH" in path_lines[0]
    assert not sentinel.exists()
