"""SR-386: the one-heavy-job lock, taken by plumb's heavy commands themselves.

``<git common dir>/plumb-heavy.lock``, created exclusively, shared by every session and
worktree. Line 1 says what the job is (people and scripts cat it); line 2 is ``pid <n>``.
``plumb heavy -- <command...>`` runs any command under it.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

HEAVY_WAIT_S = float(os.environ.get("PLUMB_HEAVY_WAIT_S") or 20.0)
HELD = "PLUMB_HEAVY_HELD"
_TURNS = threading.RLock()      # SR-388: threads of one process take turns too


def common_dir(cwd: Path) -> Path:
    out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=cwd, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout.strip()
    return Path(cwd, out)


def _holder(lock: Path) -> tuple[str, int | None]:
    """What the lock says the job is, and the pid of its holder (None: none written)."""
    try:
        lines = lock.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", None
    pid = lines[1].split() if len(lines) > 1 else []
    return (lines[0] if lines else ""), (int(pid[1]) if len(pid) == 2 and pid[0] == "pid"
                                         and pid[1].isdigit() else None)


def _dead(pid: int | None) -> bool:
    # shortcut: no takeover on Windows (os.kill(pid, 0) would terminate the process), and a
    # lock with no pid line is only waited for; upgrade with a Windows process probe if needed.
    if pid is None or os.name == "nt":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


@contextlib.contextmanager
def heavy(cwd: Path, what: str) -> Iterator[None]:
    """The lock of ``_heavy``, one thread of the process at a time (the same thread may go in
    again)."""
    with _TURNS, _heavy(cwd, what):
        yield


@contextlib.contextmanager
def _heavy(cwd: Path, what: str) -> Iterator[None]:
    """Hold the lock for the block: wait while another job holds it (saying once what for),
    take over a lock whose holder is gone. Does nothing under a holder (``PLUMB_HEAVY_HELD``)."""
    if os.environ.get(HELD):
        yield
        return
    lock = common_dir(Path(cwd)) / "plumb-heavy.lock"
    told = False
    while True:
        try:
            with open(lock, "x", encoding="utf-8") as fh:
                fh.write(f"{' '.join(what.split())}\npid {os.getpid()}\n")
            break
        except (FileExistsError, PermissionError):
            job, pid = _holder(lock)
            if _dead(pid):
                print(f"plumb: taking over the heavy lock of process {pid}, no longer "
                      f"running: {job}", file=sys.stderr)
                if _holder(lock)[1] == pid:    # still the dead one: another taker may have won
                    lock.unlink(missing_ok=True)
                continue
            if not told:
                print(f"plumb: waiting for {job or 'another heavy job'}"
                      + ("" if pid else " (a lock written by hand: if it is your own, run the "
                         "command through `plumb heavy --` or set PLUMB_HEAVY_HELD=1)"),
                      file=sys.stderr)
                told = True
            time.sleep(HEAVY_WAIT_S)
    os.environ[HELD] = "1"
    try:
        yield
    finally:
        del os.environ[HELD]
        lock.unlink(missing_ok=True)


def run(command: str, argv: list[str]) -> int:
    """``plumb heavy -- <command...>``: run it under the lock; exit with its exit code."""
    cmd = argv[1:] if argv[:1] == ["--"] else argv
    if not cmd or cmd[0] in ("-h", "--help"):
        print("usage: plumb heavy -- <command...>   run a command under the one-heavy-job lock")
        return 0 if cmd else 2
    with heavy(Path.cwd(), "plumb heavy: " + " ".join(cmd)):
        try:
            return subprocess.run(cmd).returncode
        except OSError as exc:
            print(f"plumb: {exc}", file=sys.stderr)
            return 127
