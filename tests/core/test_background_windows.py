"""A background plumb process opens no console window on Windows, for itself or for what it
runs, and still outlives the process that started it (the owner: "Why are there still windows
spawning during executions?")."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from plumb.background import popen_options

windows_only = pytest.mark.skipif(os.name != "nt", reason="console windows are a Windows thing")

PROBE = '''
import ctypes, json, subprocess, sys
out, role = sys.argv[1], sys.argv[2]
h = ctypes.windll.kernel32.GetConsoleWindow()
visible = bool(ctypes.windll.user32.IsWindowVisible(h)) if h else False
with open(out, "a", encoding="utf-8") as f:
    f.write(json.dumps({"role": role, "console": bool(h), "visible": visible}) + "\\n")
if role == "child":
    subprocess.run([sys.executable, __file__, out, "grandchild"])   # a plain call, like git
'''

LINGER = '''
import sys, time
for n in range(4):
    time.sleep(0.3)
    with open(sys.argv[1], "a", encoding="utf-8") as f:
        f.write(f"alive {n}\\n")
'''


def _wait_for(path: Path, lines: int, seconds: float = 20.0) -> list[str]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and len(path.read_text(encoding="utf-8").splitlines()) >= lines:
            break
        time.sleep(0.1)
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


@windows_only
def test_ex1_ex2_neither_the_process_nor_what_it_runs_gets_a_console_window(
        tmp_path: Path) -> None:
    probe, out = tmp_path / "probe.py", tmp_path / "out.jsonl"
    probe.write_text(PROBE, encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(probe), str(out), "child"],
                            **popen_options(tmp_path))
    proc.wait(timeout=60)
    rows = [json.loads(line) for line in _wait_for(out, 2)]
    assert [r["role"] for r in rows] == ["child", "grandchild"]
    assert all(not r["console"] and not r["visible"] for r in rows), rows


@windows_only
def test_the_flags_never_detach_the_console() -> None:
    flags = popen_options(".")["creationflags"]
    assert flags & subprocess.CREATE_NO_WINDOW
    assert not flags & subprocess.DETACHED_PROCESS


def test_ex3_the_process_outlives_the_one_that_started_it(tmp_path: Path) -> None:
    linger, out = tmp_path / "linger.py", tmp_path / "alive.txt"
    linger.write_text(LINGER, encoding="utf-8")
    starter = (f"import subprocess, sys; from plumb.background import popen_options; "
               f"subprocess.Popen([sys.executable, {str(linger)!r}, {str(out)!r}], "
               f"**popen_options({str(tmp_path)!r}))")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [
        str(Path(__file__).resolve().parents[2] / "src"), os.environ.get("PYTHONPATH")]))}
    subprocess.run([sys.executable, "-c", starter], check=True, env=env, timeout=60)
    assert len(_wait_for(out, 4)) == 4         # the starter is long gone; the child finished


def test_ex4_elsewhere_the_process_starts_its_own_session() -> None:
    options = popen_options(".")
    if os.name == "nt":
        assert "start_new_session" not in options
    else:
        assert options["start_new_session"] is True and "creationflags" not in options
    assert options["stdin"] is subprocess.DEVNULL and options["close_fds"] is True
