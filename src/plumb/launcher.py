"""How git reaches plumb: the only place that spells it (SP7 4.6, SR-083, DEC-023).

Under the Claude Code plugin (``PLUMB_PLUGIN_ROOT`` set by the plugin's ``bin/plumb``) git's
hooks and the record merge driver call the user-level launcher ``PLUMB_HOME/bin/plumb``, so
they follow plugin updates without being rewritten, and each hook script starts with a guard:
on a machine without the plugin (a teammate, a build server) it prints one line and lets git
go on. Outside the plugin (the legacy CLI-only use) they keep today's interpreter path,
``"<python>" -m plumb``.

``PLUMB_HOME`` is ``$PLUMB_HOME``, else ``$CLAUDE_PLUGIN_DATA`` (set by Claude Code for a
plugin's hooks), else ``~/.plumb``. Standard library only."""

from __future__ import annotations

import os
from pathlib import Path

NOT_SET_UP = {
    "push": "plumb is not set up on this machine; this push was not checked",
    "merge": "plumb is not set up on this machine; this merge was not checked",
    "commit": "plumb is not set up on this machine; this commit was not checked",
}
_HOOK_KIND = {"pre-push": "push", "post-merge": "merge", "pre-merge-commit": "merge"}


def plugin_root() -> str | None:
    """The plugin's root when plumb runs from the plugin's environment, else ``None``."""
    return os.environ.get("PLUMB_PLUGIN_ROOT") or None


def plumb_home() -> Path:
    """The plugin's data directory (SP7 4.2)."""
    for name in ("PLUMB_HOME", "CLAUDE_PLUGIN_DATA"):
        value = os.environ.get(name)
        if value:
            return Path(value)
    return Path.home() / ".plumb"


def _slashes(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def user_launcher() -> str:
    """``PLUMB_HOME/bin/plumb``, with forward slashes (git's hooks run in sh)."""
    return _slashes(plumb_home() / "bin" / "plumb")


def prefix(interpreter: str) -> str:
    """What a git hook or the merge driver runs to call plumb: the user-level launcher under
    the plugin, else ``"<interpreter>" -m plumb``."""
    if plugin_root():
        return f'"{user_launcher()}"'
    return f'"{_slashes(interpreter)}" -m plumb'


def hook_guard(hook: str) -> str:
    """The guard line a git hook starts with under the plugin (empty outside it): no launcher
    on this machine, one plain line and exit 0."""
    if not plugin_root():
        return ""
    line = NOT_SET_UP[_HOOK_KIND.get(hook, "commit")]
    return f'[ -f "{user_launcher()}" ] || {{ echo "{line}"; exit 0; }}\n'


def git_hook_line(interpreter: str, hook: str, args: str) -> str:
    """The guard and the ``exec`` line of one of plumb's git hooks."""
    return f"{hook_guard(hook)}exec {prefix(interpreter)} {args}\n"


def driver_command(interpreter: str) -> str:
    """The launcher the record merge driver's command starts with."""
    return prefix(interpreter)
