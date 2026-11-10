"""How iaso starts a background process: one that outlives the hook or command that
started it, quiet on stdio, and on Windows with no console window of its own nor for anything
it runs.

The flag is ``CREATE_NO_WINDOW`` with a new process group. ``DETACHED_PROCESS`` is never used:
it gives the child no console at all, and then every git, pytest or model command the child
runs allocates a visible one, which is the stream of windows the owner saw. On other systems
the process starts its own session."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

NO_WINDOW = 0x08000000           # subprocess.CREATE_NO_WINDOW
NEW_PROCESS_GROUP = 0x00000200   # subprocess.CREATE_NEW_PROCESS_GROUP


def popen_options(cwd: Path | str) -> dict[str, Any]:
    """Keyword arguments for ``subprocess.Popen`` of a background iaso process."""
    options: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                               "stderr": subprocess.DEVNULL, "cwd": str(cwd),
                               "close_fds": True}
    if os.name == "nt":
        options["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", NO_WINDOW)
                                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP",
                                              NEW_PROCESS_GROUP))
    else:
        options["start_new_session"] = True
    return options
