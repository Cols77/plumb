"""Shared helpers of the plugin's tests (SP7 4.8): run the plugin's sh scripts with a controlled
PATH, fake interpreters that record how they were called, and a plumb home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugin"
HOOK = PLUGIN / "bin" / "plumb-hook"
LAUNCHER = PLUGIN / "bin" / "plumb"
SH = shutil.which("sh")
needs_sh = pytest.mark.skipif(SH is None, reason="no POSIX sh on this machine")
EVENTS = ("session-start", "prompt", "pre-tool", "post-edit", "edit-check", "stop")


def tools_dir() -> str:
    """The folder of sh and its usual tools (cat, find, mkdir, mv, rm, sleep, ls, cygpath)."""
    assert SH is not None
    return str(Path(SH).parent)


def slashes(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def manifest() -> dict[str, str]:
    return json.loads((PLUGIN / "vendor" / "MANIFEST.json").read_text(encoding="utf-8"))


def write_script(path: Path, body: str) -> Path:
    """A ``#!/bin/sh`` script at ``path`` (LF line ends, executable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("#!/bin/sh\n" + body.rstrip("\n") + "\n").encode("utf-8"))
    path.chmod(0o755)
    return path


def sentinel_bin(folder: Path, sentinel: Path, names: Sequence[str] = (
        "python", "python3", "python3.12", "plumb", "uv", "py")) -> Path:
    """Programs that must never run: each appends its name to ``sentinel``."""
    for name in names:
        write_script(folder / name, f'echo "{name} $*" >> "{slashes(sentinel)}"\nexit 0')
    return folder


def recording_python(path: Path, log: Path) -> Path:
    """The bundled environment's interpreter, faked: it records its arguments and the plugin
    root it was given, and reads its stdin."""
    return write_script(path, (
        f'printf "argv:%s\\n" "$*" >> "{slashes(log)}"\n'
        f'printf "root:%s\\n" "$PLUMB_PLUGIN_ROOT" >> "{slashes(log)}"\n'
        "cat > /dev/null\n"))


def real_python(path: Path) -> Path:
    """An interpreter script that runs this checkout's plumb (the bundled environment, real)."""
    src = slashes(REPO / "src")
    return write_script(path, f'export PYTHONPATH="{src}"\nexec "{slashes(sys.executable)}" "$@"')


def ready_home(home: Path, python: Path) -> Path:
    """``home`` with a ``current.json`` naming ``python`` for the plugin's wheel."""
    home.mkdir(parents=True, exist_ok=True)
    data = {"python": slashes(python), "version": manifest()["version"],
            "wheel_sha256": manifest()["sha256"], "plugin_root": slashes(PLUGIN)}
    (home / "current.json").write_text(json.dumps(data), encoding="utf-8")
    return home


def user_launcher(home: Path) -> Path:
    """``home/bin/plumb`` as the bootstrap writes it, running this checkout's plumb."""
    src = slashes(REPO / "src")
    return write_script(home / "bin" / "plumb", (
        f'export PLUMB_HOME="{slashes(home)}" PLUMB_PLUGIN_ROOT="{slashes(PLUGIN)}" '
        f'PYTHONPATH="{src}"; exec "{slashes(sys.executable)}" -m plumb "$@"'))


def env_with(path: Sequence[Path | str] = (), **values: str) -> dict[str, str]:
    """The test's environment with ``PATH`` = ``path`` then sh's tools only, and ``values``."""
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([*(str(p) for p in path), tools_dir()])
    env.update(values)
    return env


def run_hook(event: str, cwd: Path, data: Mapping[str, object] | str | None = None,
             env: Mapping[str, str] | None = None, timeout: float = 60
             ) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    text = data if isinstance(data, str) else json.dumps(data or {"session_id": "s1"})
    return subprocess.run([SH, slashes(HOOK), event], input=text, cwd=cwd,
                          env=dict(env or env_with()), capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8")


def git(root: Path, *args: str, env: Mapping[str, str] | None = None, check: bool = True
        ) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", check=check, env=dict(env) if env else None)


def git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    return root


def adopted_repo(root: Path) -> Path:
    from plumb.commands import init_repo

    git_repo(root)
    init_repo(root)
    return root


def hook_data(event: str, **fields: object) -> dict[str, object]:
    data: dict[str, object] = {"session_id": "s1", "hook_event_name": event, "cwd": "."}
    if event == "session-start":
        data["source"] = "startup"
    if event == "pre-tool":
        data.update(tool_name="Bash", tool_input={"command": "plumb status"})
    if event in ("post-edit", "edit-check"):
        data.update(tool_name="Edit", tool_input={"file_path": "src/app.py"})
    data.update(fields)
    return data
