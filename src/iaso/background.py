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

# What a git hook exports. Inherited, they point every git the child runs (a scratch repository's
# `git init`, a test fixture's) at the hook's repository: a worktree's GIT_DIR makes `git init`
# write core.bare=true and core.fileMode=true into the shared config (report-2680054f).
GIT_HOOK_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                 "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE", "GIT_PREFIX")


def child_env(drop: tuple[str, ...] = ()) -> dict[str, str]:
    """This process's environment without the git hook variables nor ``drop``: git in the child
    finds its repository from its own working directory."""
    return {k: v for k, v in os.environ.items() if k not in GIT_HOOK_VARS and k not in drop}


def popen_options(cwd: Path | str, drop: tuple[str, ...] = ()) -> dict[str, Any]:
    """Keyword arguments for ``subprocess.Popen`` of a background iaso process, its
    environment ``child_env(drop)``."""
    options: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                               "stderr": subprocess.DEVNULL, "cwd": str(cwd),
                               "close_fds": True, "env": child_env(drop)}
    if os.name == "nt":
        options["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", NO_WINDOW)
                                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP",
                                              NEW_PROCESS_GROUP))
    else:
        options["start_new_session"] = True
    return options
