"""The plugin's launchers after the plugin review (SR-119, SR-121, SR-123 EX-2 and EX-3): the
setup reports its own failure, one probe finds a Python under any of its names, the gate is found
from a subfolder and is not silenced by a deny rule, and the guard looks at the tool's input
only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from plumb.present import owner_text

from .helpers import (
    LAUNCHER,
    PLUGIN,
    SH,
    adopted_repo,
    env_with,
    hook_data,
    manifest,
    needs_sh,
    ready_home,
    recording_python,
    run_hook,
    sentinel_bin,
    slashes,
    tools_dir,
    write_script,
)

pytestmark = [needs_sh]
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def _no_python_beside_sh() -> None:
    names = ("uv", "python3.12", "python3", "python", "py")
    for name in names:
        for suffix in ("", ".exe"):
            if (Path(tools_dir()) / f"{name}{suffix}").exists():
                pytest.skip(f"this machine has {name} beside sh")


def _bootstrap(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    return subprocess.run([SH, slashes(LAUNCHER), "--plumb-bootstrap"], env=env,
                          capture_output=True, text=True, timeout=120, input="")


def _env_name() -> str:
    return f"{manifest()['version']}-{manifest()['sha256'][:12]}"


def _fake_python(path: Path, log: Path, version_ok: bool = True, flag: str = "") -> Path:
    """A system Python, faked: the version check answers ``version_ok``; ``-m venv DIR`` makes
    DIR with a recording interpreter. With ``flag`` (``py``'s ``-3.12``) it answers only when
    called with that flag first."""
    template = recording_python(path.parent / f"{path.name}-venv-python", Path(f"{log}.venv"))
    check = "exit 0" if version_ok else "exit 1"
    head = (f'[ "$1" = "{flag}" ] || exit 1\nshift\n' if flag else "")
    return write_script(path, (
        f'echo "{path.name} $*" >> "{slashes(log)}"\n'
        f"{head}"
        f'if [ "$1" = -c ]; then {check}; fi\n'
        'if [ "$1" = -m ] && [ "$2" = venv ]; then\n'
        '  mkdir -p "$3/bin"\n'
        f'  cp "{slashes(template)}" "$3/bin/python"\n'
        '  chmod +x "$3/bin/python"\n'
        'fi\n'
        'exit 0'))


# SR-119: the setup's own failure ---------------------------------------------------------------

@pytest.mark.sr("SR-119")
def test_bootstrap_without_python_exits_2(tmp_path: Path) -> None:
    """EX-1: no uv and no Python 3.12 or later: exit 2 and the plain sentence."""
    _no_python_beside_sh()
    log = tmp_path / "python.log"
    fakebin = tmp_path / "fakebin"
    _fake_python(fakebin / "python3", log, version_ok=False)  # a Python 3.11
    home = tmp_path / "home"
    result = _bootstrap(env_with([fakebin], PLUMB_HOME=str(home)))
    assert result.returncode == 2, result.stderr
    assert "plumb needs Python 3.12" in result.stderr
    assert not (home / "lock").exists()
    assert not (home / "current.json").exists()
    assert not (home / "env" / f"{_env_name()}.tmp").exists()
    assert "venv" not in log.read_text(encoding="utf-8")


@pytest.mark.sr("SR-119")
def test_failed_install_exits_non_zero_and_cleans_up(tmp_path: Path) -> None:
    """EX-2: pip fails: a non-zero exit, no half-built folder, the lock released."""
    log = tmp_path / "uv.log"
    write_script(tmp_path / "fakebin" / "uv", (
        f'echo "uv $*" >> "{slashes(log)}"\n'
        'for a; do last=$a; done\n'
        'if [ "$1" = venv ]; then mkdir -p "$last/bin"; : > "$last/bin/python"; exit 0; fi\n'
        'exit 1'))
    home = tmp_path / "home"
    result = _bootstrap(env_with([tmp_path / "fakebin"], PLUMB_HOME=str(home)))
    assert result.returncode == 1, result.stderr
    assert any(line.startswith("uv pip install")
               for line in log.read_text(encoding="utf-8").splitlines())
    assert not (home / "env" / f"{_env_name()}.tmp").exists()
    assert not (home / "env" / _env_name()).exists()
    assert not (home / "lock").exists()
    assert not (home / "current.json").exists()


def _wait_ready(home: Path, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while not (home / "current.json").exists() and time.time() < deadline:
        time.sleep(0.2)
    while (home / "lock").exists() and time.time() < deadline:
        time.sleep(0.2)


@pytest.mark.sr("SR-119")
def test_session_start_sets_up_with_python_exe_only(tmp_path: Path) -> None:
    """EX-3: python.org's Windows install (python.exe 3.12, no python3.12, no uv): the session
    start begins the setup instead of saying Python is missing, and the setup uses it."""
    _no_python_beside_sh()
    log = tmp_path / "python.log"
    fakebin = tmp_path / "fakebin"
    _fake_python(fakebin / "python", log)
    root = adopted_repo(tmp_path / "repo")
    home = tmp_path / "home"
    env = env_with([fakebin], PLUMB_HOME=str(home), CLAUDE_PROJECT_DIR=str(root))
    result = run_hook("session-start", root, hook_data("session-start"), env)
    assert json.loads(result.stdout) == {"systemMessage": owner_text.GETTING_READY}
    _wait_ready(home)
    assert (home / "current.json").is_file()
    assert not (home / "lock").exists()
    calls = log.read_text(encoding="utf-8")
    assert "python -m venv" in calls
    assert "argv:-m pip install" in Path(f"{log}.venv").read_text(encoding="utf-8")


@pytest.mark.sr("SR-119")
def test_bootstrap_with_the_py_launcher_only(tmp_path: Path) -> None:
    """The Windows launcher ``py -3.12`` is tried too, and its flag passed to every call."""
    _no_python_beside_sh()
    log = tmp_path / "py.log"
    fakebin = tmp_path / "fakebin"
    _fake_python(fakebin / "py", log, flag="-3.12")
    home = tmp_path / "home"
    result = _bootstrap(env_with([fakebin], PLUMB_HOME=str(home)))
    assert result.returncode == 0, result.stderr
    assert "py -3.12 -m venv" in log.read_text(encoding="utf-8")
    assert (home / "current.json").is_file()


@pytest.mark.sr("SR-119")
def test_probe_agrees_with_the_build(tmp_path: Path) -> None:
    _no_python_beside_sh()
    assert SH is not None
    fakebin = tmp_path / "fakebin"
    probe = [SH, slashes(LAUNCHER), "--plumb-probe"]
    env = env_with([fakebin], PLUMB_HOME=str(tmp_path / "home"))
    fakebin.mkdir()
    assert subprocess.run(probe, env=env, capture_output=True, timeout=30).returncode == 2
    _fake_python(fakebin / "python3", tmp_path / "old.log", version_ok=False)
    assert subprocess.run(probe, env=env, capture_output=True, timeout=30).returncode == 2
    _fake_python(fakebin / "python", tmp_path / "new.log")
    assert subprocess.run(probe, env=env, capture_output=True, timeout=30).returncode == 0
    assert not (tmp_path / "home" / "current.json").exists()


@pytest.mark.sr("SR-119")
def test_stale_lock_taken_over_when_find_is_not_posix(tmp_path: Path) -> None:
    """A ``find`` on the PATH that knows no -mmin (Windows' FIND.EXE) does not keep a stale lock
    in place: the POSIX find is used when the system has one."""
    if not Path("/usr/bin/find").exists() and sys.platform != "win32":
        pytest.skip("no /usr/bin/find")
    fakebin = tmp_path / "fakebin"
    write_script(fakebin / "find", 'echo "FIND: Parameter format not correct" >&2\nexit 2')
    write_script(fakebin / "uv", (
        'for a; do last=$a; done\n'
        'if [ "$1" = venv ]; then mkdir -p "$last/bin"; : > "$last/bin/python"; fi\n'
        'exit 0'))
    home = tmp_path / "home"
    (home / "lock").mkdir(parents=True)
    old = time.time() - 20 * 60
    os.utime(home / "lock", (old, old))
    assert SH is not None
    process = subprocess.run([SH, slashes(LAUNCHER), "--plumb-bootstrap"],
                             env=env_with([fakebin], PLUMB_HOME=str(home)),
                             capture_output=True, text=True, timeout=60, input="")
    assert process.returncode == 0, process.stderr
    assert (home / "current.json").is_file()
    assert not (home / "lock").exists()


# SR-121: the gate under the .plumb/ found by the walk, not silenced by a deny rule -------------

def _closed_gate(root: Path) -> None:
    gate = root / ".plumb" / "session" / "s1" / "gate"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text('{"state": "closed", "reason": "the reminders"}', encoding="utf-8")


def _poisoned(tmp_path: Path, root: Path, project_dir: Path | None = None
              ) -> tuple[dict[str, str], Path]:
    sentinel = tmp_path / "sentinel.txt"
    poison = sentinel_bin(tmp_path / "poison", sentinel)
    home = ready_home(tmp_path / "home", poison / "python")
    env = env_with([poison], PLUMB_HOME=str(home),
                   CLAUDE_PROJECT_DIR=str(project_dir or root))
    return env, sentinel


def _denied(result: subprocess.CompletedProcess[str]) -> bool:
    if not result.stdout.strip():
        return False
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def _settings(root: Path, data: dict[str, object]) -> None:
    path = root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


LEGACY_HOOK = '"$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" -m plumb hook'
LEGACY_GATE = 'sh "$CLAUDE_PROJECT_DIR/.claude/plumb/gate.sh"'


def _legacy_settings(root: Path, gate: bool) -> None:
    hooks: dict[str, object] = {
        event: [{"hooks": [{"type": "command", "command": f"{LEGACY_HOOK} {name}"}]}]
        for event, name in (("SessionStart", "session-start"), ("UserPromptSubmit", "prompt"),
                            ("Stop", "stop"))}
    if gate:
        hooks["PreToolUse"] = [{"matcher": "Edit|Write|MultiEdit|NotebookEdit",
                                "hooks": [{"type": "command", "command": LEGACY_GATE}]}]
    _settings(root, {"permissions": {"deny": ["Bash(plumb hook prompt:*)"]}, "hooks": hooks})


@pytest.mark.sr("SR-121")
@pytest.mark.parametrize("compact", [False, True])
def test_deny_rule_naming_plumb_hook_does_not_silence_the_gate(tmp_path: Path,
                                                               compact: bool) -> None:
    """EX-1: a permission rule is not a hook: the edit is refused while the gate is closed."""
    root = adopted_repo(tmp_path / "repo")
    _closed_gate(root)
    settings = {"permissions": {"deny": ["Bash(plumb hook prompt:*)",
                                         "Bash(uv run plumb hook prompt:*)"]},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}]}}
    path = root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(settings, indent=None if compact else 2), encoding="utf-8")
    env, sentinel = _poisoned(tmp_path, root)
    for tool in EDIT_TOOLS:
        result = run_hook("pre-tool", root, hook_data(
            "pre-tool", tool_name=tool, tool_input={"file_path": "src/app.py"}), env)
        assert _denied(result), (tool, result.stdout, result.stderr)
    assert not sentinel.exists()


@pytest.mark.sr("SR-121")
def test_gate_found_from_a_subfolder(tmp_path: Path) -> None:
    """EX-2: Claude Code started in src/: the gate of the repository's .plumb/ still refuses."""
    root = adopted_repo(tmp_path / "repo")
    _closed_gate(root)
    src = root / "src"
    src.mkdir()
    env, sentinel = _poisoned(tmp_path, root, project_dir=src)
    result = run_hook("pre-tool", src, hook_data(
        "pre-tool", tool_name="Write", tool_input={"file_path": "app.py"}), env)
    assert _denied(result), (result.stdout, result.stderr)
    assert "the reminders" in result.stdout
    assert not sentinel.exists()


@pytest.mark.sr("SR-121")
def test_gate_script_alone_keeps_the_project_folder() -> None:
    """The per-repository install runs gate.sh without PLUMB_ROOT: the project folder, then the
    working folder, is where the gate is read."""
    text = (Path(__file__).resolve().parents[2] / "src" / "plumb" / "hosts" / "claude_code"
            / "templates" / "gate.sh").read_text(encoding="utf-8")
    assert '"${PLUMB_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.plumb/session/$session/gate"' in text


@pytest.mark.sr("SR-121")
def test_gate_template_reads_plumb_root(tmp_path: Path) -> None:
    """gate.sh (the template the bundle copies) prefers PLUMB_ROOT, then CLAUDE_PROJECT_DIR."""
    assert SH is not None
    script = (Path(__file__).resolve().parents[2] / "src" / "plumb" / "hosts" / "claude_code"
              / "templates" / "gate.sh")
    root = tmp_path / "repo"
    _closed_gate(root)
    data = json.dumps({"session_id": "s1", "tool_name": "Edit", "tool_input": {}})
    for values, refused in (({"PLUMB_ROOT": str(root), "CLAUDE_PROJECT_DIR": str(tmp_path)}, True),
                            ({"CLAUDE_PROJECT_DIR": str(root)}, True),
                            ({"CLAUDE_PROJECT_DIR": str(tmp_path)}, False)):
        env = env_with([])
        env.pop("PLUMB_ROOT", None)
        env.update(values)
        result = subprocess.run([SH, slashes(script)], input=data, env=env, cwd=tmp_path,
                                capture_output=True, text=True, timeout=30)
        assert ('"deny"' in result.stdout) is refused, values


@pytest.mark.sr("SR-121")
@pytest.mark.parametrize("event", ["session-start", "prompt", "pre-tool", "post-edit",
                                   "edit-check", "stop"])
def test_legacy_install_runs_alone(tmp_path: Path, event: str) -> None:
    """EX-3: a legacy install whose hook commands run plumb hook (and its gate): the plugin's
    hook does nothing, so nothing runs twice."""
    root = adopted_repo(tmp_path / "repo")
    _closed_gate(root)
    _legacy_settings(root, gate=True)
    env, sentinel = _poisoned(tmp_path, root)
    data = hook_data(event)
    if event == "pre-tool":
        data.update(tool_name="Write", tool_input={"file_path": "src/plumb_app.py"})
    result = run_hook(event, root, data, env)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not sentinel.exists()


@pytest.mark.sr("SR-121")
def test_legacy_install_without_a_gate_keeps_the_plugin_gate(tmp_path: Path) -> None:
    """A legacy install that runs plumb hook but registers no gate.sh: the plugin's pre-tool
    still refuses an edit while the gate is closed, and starts no Python."""
    root = adopted_repo(tmp_path / "repo")
    _closed_gate(root)
    _legacy_settings(root, gate=False)
    env, sentinel = _poisoned(tmp_path, root)
    result = run_hook("pre-tool", root, hook_data(
        "pre-tool", tool_name="Edit", tool_input={"file_path": "src/plumb.py"}), env)
    assert _denied(result), (result.stdout, result.stderr)
    for event in ("prompt", "stop"):
        result = run_hook(event, root, hook_data(event), env)
        assert (result.returncode, result.stdout) == (0, "")
    assert not sentinel.exists()


# SR-123: the guard looks at the tool's input; plumb.cmd finds Git's sh ------------------------

@pytest.mark.sr("SR-123")
def test_repository_named_plumb_starts_no_python(tmp_path: Path) -> None:
    """EX-2: the repository's path contains 'plumb': ls starts no Python for the guard."""
    root = adopted_repo(tmp_path / "plumb-work" / "plumb")
    env, sentinel = _poisoned(tmp_path, root)
    data = hook_data("pre-tool", tool_input={"command": "ls"}, cwd=slashes(root),
                     transcript_path=slashes(tmp_path / ".claude" / "plumb" / "t.jsonl"))
    result = run_hook("pre-tool", root, data, env)
    assert (result.returncode, result.stdout) == (0, "")
    assert not sentinel.exists()
    # a call that names plumb still reaches the guard
    data["tool_input"] = {"command": "plumb approve SR-001"}
    run_hook("pre-tool", root, data, env)
    assert sentinel.exists()


@pytest.mark.sr("SR-123")
@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe")
def test_plumb_cmd_finds_git_sh(tmp_path: Path) -> None:
    """EX-3: cmd.exe without sh on its PATH: plumb.cmd runs plumb with Git for Windows' sh."""
    import shutil

    git = shutil.which("git")
    if git is None:
        pytest.skip("no git")
    # Git for Windows' own folder: the one whose bin holds sh.exe; its cmd/ holds no sh
    install = next((p for p in Path(git).resolve().parents if (p / "bin" / "sh.exe").exists()),
                   None)
    if install is None or not (install / "cmd" / "git.exe").exists():
        pytest.skip("git is not Git for Windows")
    git_cmd = install / "cmd"
    assert not (git_cmd / "sh.exe").exists()
    log = tmp_path / "bundled.log"
    home = ready_home(tmp_path / "home", recording_python(tmp_path / "env" / "python", log))
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    env = dict(os.environ, PATH=os.pathsep.join([str(git_cmd), str(system32)]),
               PLUMB_HOME=str(home))
    result = subprocess.run(["cmd.exe", "/c", str(PLUGIN / "bin" / "plumb.cmd"), "status"],
                            env=env, capture_output=True, text=True, timeout=60, input="")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "argv:-m plumb status" in log.read_text(encoding="utf-8")


# after the second review: the probe before any folder, plumb.cmd's home, the guard's cut,
# a value ending in an escaped backslash, the legacy gate from a subfolder ---------------------

@pytest.mark.sr("SR-119")
def test_bootstrap_without_python_creates_no_folders(tmp_path: Path) -> None:
    """EX-1: no Python: the setup leaves nothing under PLUMB_HOME (no empty env/ or bin/)."""
    _no_python_beside_sh()
    fakebin = tmp_path / "fakebin"
    _fake_python(fakebin / "python3", tmp_path / "python.log", version_ok=False)
    home = tmp_path / "home"
    result = _bootstrap(env_with([fakebin], PLUMB_HOME=str(home)))
    assert result.returncode == 2, result.stderr
    assert not (home / "env").exists()
    assert not (home / "bin").exists()


@pytest.mark.sr("SR-119")
@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe reads Windows paths")
def test_user_plumb_cmd_names_home_as_windows_does(tmp_path: Path) -> None:
    """PLUMB_HOME/bin/plumb.cmd sets PLUMB_HOME as C:/..., never /c/... (which a Windows
    python.exe started from cmd.exe would read as a folder c under the current drive)."""
    log = tmp_path / "py.log"
    fakebin = tmp_path / "fakebin"
    _fake_python(fakebin / "py", log, flag="-3.12")
    home = tmp_path / "home"
    result = _bootstrap(env_with([fakebin], PLUMB_HOME=slashes(home)))
    if result.returncode != 0 and "needs Python" in result.stderr:
        pytest.skip("a real Python beside sh answers first")
    assert result.returncode == 0, result.stderr
    text = (home / "bin" / "plumb.cmd").read_text(encoding="utf-8")
    line = next(part for part in text.split("\r\n") if part.startswith('@set "PLUMB_HOME='))
    assert line[len('@set "PLUMB_HOME='):][1] == ":", line


@pytest.mark.sr("SR-123")
def test_keys_after_the_tool_input_start_no_python(tmp_path: Path) -> None:
    """EX-2: tool_use_id and permission_mode come after tool_input; a value naming the
    repository there does not count as the call naming plumb."""
    root = adopted_repo(tmp_path / "repo")
    env, sentinel = _poisoned(tmp_path, root)
    data = ('{"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": "Bash", '
            '"tool_input": {"command": "ls"}, "tool_use_id": "toolu_plumb_1", '
            '"permission_mode": "plumb-default"}')
    result = run_hook("pre-tool", root, data, env)
    assert (result.returncode, result.stdout) == (0, "")
    assert not sentinel.exists()


@pytest.mark.sr("SR-121")
def test_a_command_ending_in_a_backslash_is_read_to_its_quote(tmp_path: Path) -> None:
    """EX-3: a hook command ending in an escaped backslash closes at its quote, so the next
    hook's command (here the old install's `plumb hook stop`) is still read and the plugin's
    hook stays out of the way."""
    root = adopted_repo(tmp_path / "repo")
    path = root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    hooks = [{"command": "cd C:\\dir\\"},
             {"command": "python -m plumb hook stop", "type": "command"}]
    path.write_text(json.dumps({"hooks": {"Stop": [{"hooks": hooks}]}}), encoding="utf-8")
    assert '"cd C:\\\\dir\\\\"' in path.read_text(encoding="utf-8")
    env, sentinel = _poisoned(tmp_path, root)
    result = run_hook("stop", root, hook_data("stop"), env)
    assert (result.returncode, result.stdout) == (0, "")
    assert not sentinel.exists()


@pytest.mark.sr("SR-121")
def test_legacy_gate_found_from_a_subfolder(tmp_path: Path) -> None:
    """The per-repository gate.sh, run with no PLUMB_ROOT from a session started in src/,
    reads the gate of the .plumb/ above it; the walk stops at the git root."""
    assert SH is not None
    script = (Path(__file__).resolve().parents[2] / "src" / "plumb" / "hosts" / "claude_code"
              / "templates" / "gate.sh")
    root = adopted_repo(tmp_path / "repo")
    _closed_gate(root)
    src = root / "src" / "deep"
    src.mkdir(parents=True)
    data = json.dumps({"session_id": "s1", "tool_name": "Edit", "tool_input": {}})
    env = env_with([])
    env.pop("PLUMB_ROOT", None)
    env["CLAUDE_PROJECT_DIR"] = str(src)
    result = subprocess.run([SH, slashes(script)], input=data, env=env, cwd=src,
                            capture_output=True, text=True, timeout=30)
    assert '"deny"' in result.stdout
    inner = git_repo_at(src / "nested")
    env["CLAUDE_PROJECT_DIR"] = str(inner)
    result = subprocess.run([SH, slashes(script)], input=data, env=env, cwd=inner,
                            capture_output=True, text=True, timeout=30)
    assert result.stdout == ""


def git_repo_at(folder: Path) -> Path:
    from .helpers import git_repo

    return git_repo(folder)
