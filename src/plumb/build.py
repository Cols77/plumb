"""Which plumb build Claude Code runs, against main's (SR-358): the loaded plugin's vendored
source digest beside the ``plugin/vendor/MANIFEST.json`` committed on main, so a worktree or a
checkout compares with main's build, not its own. Nothing is reinstalled."""

from __future__ import annotations

import json
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


def outdated(root: Path | str, branch: str = "main") -> tuple[bool, str]:
    """``(True, "<main's build date>")`` when the plugin plumb runs from (``PLUMB_PLUGIN_ROOT``,
    set by the plugin's launcher) was built from another source than the manifest committed on
    ``branch``; ``(False, "")`` otherwise, or when plumb does not run from a plugin or either
    manifest is missing (a repository other than plumb's own has no build of plumb)."""
    from plumb.launcher import plugin_root

    loaded = plugin_root()
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
