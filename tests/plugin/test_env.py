"""The bundled environment (SP7 4.2, DEC-023; SR-082 EX-2, EX-3): every hook runs plumb from the
plugin's own environment, never the repository's .venv or a plumb on the PATH; the environment
is set up once, safely when two sessions start together; git's hooks and the merge driver call
the user-level launcher."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from plumb.present import owner_text

from .helpers import (
    EVENTS,
    LAUNCHER,
    PLUGIN,
    SH,
    adopted_repo,
    env_with,
    git,
    hook_data,
    manifest,
    needs_sh,
    ready_home,
    recording_python,
    run_hook,
    sentinel_bin,
    slashes,
    write_script,
)

pytestmark = [needs_sh, pytest.mark.sr("SR-082")]


def _poisoned_repo(root: Path, sentinel: Path) -> Path:
    """An adopted repository whose own .venv holds a plumb that must never run."""
    adopted_repo(root)
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        write_script(root / rel, f'echo "repo venv $*" >> "{slashes(sentinel)}"')
    package = root / ".venv" / "Lib" / "site-packages" / "plumb"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f"open({str(sentinel)!r}, 'a').write('repo plumb imported\\n')\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("event", EVENTS)
def test_hook_uses_bundled_env(tmp_path: Path, event: str) -> None:
    sentinel = tmp_path / "sentinel.txt"
    log = tmp_path / "bundled.log"
    root = _poisoned_repo(tmp_path / "repo", sentinel)
    home = ready_home(tmp_path / "home", recording_python(tmp_path / "env" / "python", log))
    env = env_with([sentinel_bin(tmp_path / "poison", sentinel)], PLUMB_HOME=str(home),
                   CLAUDE_PROJECT_DIR=str(root))
    result = run_hook(event, root, hook_data(event), env)
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert f"argv:-m plumb hook {event}" in calls
    assert any(line.startswith("root:") and line.endswith("/plugin") for line in calls)
    assert not sentinel.exists(), sentinel.read_text(encoding="utf-8")


def _fake_uv(folder: Path, log: Path, delay: int = 1) -> Path:
    """``uv`` faked: ``uv venv DIR`` makes DIR with a recording interpreter (and waits a little,
    so two sessions overlap); ``uv pip install`` succeeds. Every call is logged."""
    python = recording_python(folder / "python-template", Path(f"{log}.python"))
    write_script(folder / "uv", (
        f'echo "uv $*" >> "{slashes(log)}"\n'
        'for a; do last=$a; done\n'
        'if [ "$1" = venv ]; then\n'
        '  mkdir -p "$last/bin"\n'
        f'  cp "{slashes(python)}" "$last/bin/python"\n'
        '  chmod +x "$last/bin/python"\n'
        f'  sleep {delay}\n'
        'fi\n'
        'exit 0'))
    return folder


def _bootstrap(env: dict[str, str]) -> subprocess.Popen[str]:
    assert SH is not None
    return subprocess.Popen([SH, slashes(LAUNCHER), "--plumb-bootstrap"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_bootstrap_lock(tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    home = tmp_path / "home"
    env = env_with([_fake_uv(tmp_path / "fakebin", log)], PLUMB_HOME=str(home))
    first, second = _bootstrap(env), _bootstrap(env)
    for process in (first, second):
        _, err = process.communicate(timeout=120)
        assert process.returncode == 0, err
    venvs = [line for line in log.read_text(encoding="utf-8").splitlines()
             if line.startswith("uv venv")]
    assert len(venvs) == 1
    current = json.loads((home / "current.json").read_text(encoding="utf-8"))
    assert current["wheel_sha256"] == manifest()["sha256"]
    assert current["version"] == manifest()["version"]
    assert Path(current["python"]).is_file()
    assert (home / "bin" / "plumb").is_file() and (home / "bin" / "plumb.cmd").is_file()
    assert not (home / "lock").exists()
    name = f"{manifest()['version']}-{manifest()['sha256'][:12]}"
    assert (home / "env" / name).is_dir() and not (home / "env" / f"{name}.tmp").exists()
    installs = [line for line in log.read_text(encoding="utf-8").splitlines()
                if line.startswith("uv pip install")]
    assert len(installs) == 1 and manifest()["wheel"] in installs[0]


def test_stale_lock_taken_over(tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    home = tmp_path / "home"
    (home / "lock").mkdir(parents=True)
    old = time.time() - 20 * 60
    os.utime(home / "lock", (old, old))
    env = env_with([_fake_uv(tmp_path / "fakebin", log, delay=0)], PLUMB_HOME=str(home))
    process = _bootstrap(env)
    _, err = process.communicate(timeout=60)
    assert process.returncode == 0, err
    assert (home / "current.json").is_file()
    assert not (home / "lock").exists()


def test_launcher_runs_the_bundled_python(tmp_path: Path) -> None:
    """``bin/plumb`` (the agent's ``plumb``) builds the environment when needed, then runs
    plumb with it, never a plumb on the PATH."""
    log = tmp_path / "uv.log"
    sentinel = tmp_path / "sentinel.txt"
    home = tmp_path / "home"
    env = env_with([_fake_uv(tmp_path / "fakebin", log, delay=0),
                    sentinel_bin(tmp_path / "poison", sentinel, ("python", "python3", "plumb"))],
                   PLUMB_HOME=str(home))
    assert SH is not None
    result = subprocess.run([SH, slashes(LAUNCHER), "status"], env=env, capture_output=True,
                            text=True, timeout=60, input="")
    assert result.returncode == 0, result.stderr
    assert "argv:-m plumb status" in Path(f"{log}.python").read_text(encoding="utf-8")
    assert not sentinel.exists()


def test_getting_ready_line(tmp_path: Path) -> None:
    log = tmp_path / "uv.log"
    sentinel = tmp_path / "sentinel.txt"
    root = adopted_repo(tmp_path / "repo")
    home = tmp_path / "home"
    env = env_with([_fake_uv(tmp_path / "fakebin", log, delay=0),
                    sentinel_bin(tmp_path / "poison", sentinel, ("python", "python3", "plumb"))],
                   PLUMB_HOME=str(home), CLAUDE_PROJECT_DIR=str(root))
    # not ready: every hook but the session start exits at once, silently
    for event in ("prompt", "pre-tool", "stop"):
        result = run_hook(event, root, hook_data(event), env)
        assert (result.returncode, result.stdout) == (0, "")
    result = run_hook("session-start", root, hook_data("session-start"), env)
    assert json.loads(result.stdout) == {"systemMessage": owner_text.GETTING_READY}
    deadline = time.time() + 60
    while not (home / "current.json").exists() and time.time() < deadline:
        time.sleep(0.2)
    while (home / "lock").exists() and time.time() < deadline:
        time.sleep(0.2)
    assert (home / "current.json").is_file()
    assert not sentinel.exists()


def test_missing_prerequisites_line(tmp_path: Path) -> None:
    root = adopted_repo(tmp_path / "repo")
    env = env_with([], PLUMB_HOME=str(tmp_path / "home"), CLAUDE_PROJECT_DIR=str(root))
    if any((Path(p) / name).exists() for p in env["PATH"].split(os.pathsep)
           for name in ("uv", "uv.exe", "python3.12", "python3.12.exe")):
        pytest.skip("this machine has uv or python3.12 beside sh")
    result = run_hook("session-start", root, hook_data("session-start"), env)
    assert json.loads(result.stdout) == {"systemMessage": owner_text.NEEDS_PYTHON}


def _plugin_env(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("PLUMB_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setenv("PLUMB_HOME", str(home))


def test_git_hooks_use_user_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import launcher
    from plumb.cli import main

    home = tmp_path / "home"
    _plugin_env(monkeypatch, home)
    root = adopted_repo(tmp_path / "repo")
    assert main(["init", "--root", str(root)]) == 0
    hooks = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip()) / "hooks"
    for name in ("commit-msg", "pre-merge-commit", "prepare-commit-msg", "post-merge",
                 "pre-push"):
        text = (hooks / name).read_text(encoding="utf-8")
        assert f'exec "{launcher.user_launcher()}" ' in text, name
        assert "-m plumb" not in text, name
        assert f'[ -f "{launcher.user_launcher()}" ] ||' in text, name


def test_driver_uses_user_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import launcher
    from plumb.cli import main

    _plugin_env(monkeypatch, tmp_path / "home")
    root = adopted_repo(tmp_path / "repo")
    assert main(["init", "--root", str(root)]) == 0
    driver = git(root, "config", "--get", "merge.plumb-record.driver").stdout.strip()
    assert driver.startswith(f'"{launcher.user_launcher()}" merge-driver')


def test_outside_the_plugin_hooks_keep_the_interpreter(tmp_path: Path) -> None:
    """The legacy CLI-only use keeps today's interpreter path (SR-084 EX-3)."""
    import sys

    from plumb.boundary import prepush

    assert prepush.hook_text(sys.executable).endswith(
        f'exec "{slashes(sys.executable)}" -m plumb merge-check --hook pre-push\n')
