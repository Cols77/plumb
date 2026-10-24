"""Which plumb build Claude Code runs, against main's (SR-357, SR-358): the loaded plugin's
vendored source digest beside the ``plugin/vendor/MANIFEST.json`` committed on main, so a
worktree or a checkout compares with main's build, not its own. Nothing is reinstalled."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

MANIFEST = "plugin/vendor/MANIFEST.json"


def _digest(text: str | None) -> str:
    try:
        return str(json.loads(text or "").get("source_digest") or "")
    except (ValueError, AttributeError):
        return ""


def _git(root: Path | str, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=2.0)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _plugin(root: Path | str) -> str:
    """The loaded plugin's folder: the hook's or the plugin ``plumb``'s environment, else the
    one this session's start hook recorded in ``host.json`` (a plain Bash or a background job
    has neither variable)."""
    for name in ("CLAUDE_PLUGIN_ROOT", "PLUMB_PLUGIN_ROOT"):
        if os.environ.get(name):
            return os.environ[name]
    from plumb import stale

    host = Path(root) / ".plumb" / "session" / stale.current_session(root) / "host.json"
    try:
        data = json.loads(host.read_text("utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("plugin") or "") if isinstance(data, dict) else ""


def outdated(root: Path | str, branch: str = "main") -> tuple[bool, str]:
    """``(True, "<main's build date>")`` when the loaded plugin was built from another source
    than the manifest committed on ``branch``; ``(False, "")`` otherwise, or when no plugin runs
    this session or either manifest is missing (a repository other than plumb's own has no
    build of plumb)."""
    loaded = _plugin(root)
    try:
        ours = _digest((Path(loaded) / "vendor" / "MANIFEST.json").read_text("utf-8")
                       if loaded else "")
    except OSError:
        ours = ""
    if not ours:
        return False, ""
    theirs = _digest(_git(root, "show", f"{branch}:{MANIFEST}"))
    if not theirs or ours == theirs:
        return False, ""
    # the build date is the commit date of main's manifest: a checkout resets mtimes
    built = (_git(root, "log", "-1", "--format=%cs", branch, "--", MANIFEST) or "").strip()
    return True, built
