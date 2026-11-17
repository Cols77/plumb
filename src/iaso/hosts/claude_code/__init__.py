"""The Claude Code adapter: hooks, status line, skill, slash command and installer (spec 6)."""

import os
import shutil
from pathlib import Path

# where claude's installers put the command: the native installer, npm with a user prefix, bun
INSTALL_DIRS = (".claude/local", ".local/bin", ".npm-global/bin", ".bun/bin")


def claude_binary(path: str | None = None) -> str | None:
    """The installed claude command: on ``path`` (default: this process's PATH) first, then in
    the folders its installers use, so a process started with a PATH that lost it (a desktop
    terminal, a background job: report-f5491971) still finds it. None when it is not installed."""
    found = shutil.which("claude", path=path)
    if found:
        return found
    return shutil.which("claude", path=os.pathsep.join(_install_folders()))


def _install_folders() -> list[str]:
    folders = [str(Path.home() / d) for d in INSTALL_DIRS]
    if os.environ.get("APPDATA"):   # npm's global folder on Windows
        folders.append(str(Path(os.environ["APPDATA"]) / "npm"))
    return folders


def claude_missing(path: str | None = None) -> str:
    """Why ``claude_binary(path)`` found nothing, in plain words: an update caught halfway (the
    installer's ``.claude-*`` temporary file where the command should be) says so, so it is not
    read as "not installed"."""
    folders = [*(path if path is not None else os.environ.get("PATH", "")).split(os.pathsep),
               *_install_folders()]
    for folder in filter(None, folders):
        try:
            if any(f.name.startswith(".claude-") for f in Path(folder).iterdir()):
                return "the claude command is being updated: try again in a minute"
        except OSError:
            continue
    return "the claude command was not found on this machine"
