"""Which plumb build Claude Code runs, against the one in plumb's own repository (SR-357,
SR-358): the loaded plugin's vendored source digest beside the ``MANIFEST.json`` on the
repository's main, whatever the install route and the session's repository. The repository is
the ``repository`` the plugin's ``plugin.json`` names; the answer is kept a while so a hook
reaches the network at most once per ``KEEP_S``. Nothing is reinstalled."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

MANIFEST = "plugin/vendor/MANIFEST.json"
KEEP_S = 900
TIMEOUT_S = 3.0
_GITHUB = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _plugin(root: Path | str) -> str:
    """The loaded plugin's folder: the hook's or the plugin ``plumb``'s environment, else the
    one this session's start hook recorded in ``host.json`` (a plain Bash or a background job
    has neither variable)."""
    for name in ("CLAUDE_PLUGIN_ROOT", "PLUMB_PLUGIN_ROOT"):
        if os.environ.get(name):
            return os.environ[name]
    from plumb import stale

    host = Path(root) / ".plumb" / "session" / stale.current_session(root) / "host.json"
    return str(_read(host).get("plugin") or "")


def _fetch(url: str) -> str:
    """The source digest of ``MANIFEST`` on ``url``'s main; "" when it cannot be read."""
    import urllib.request

    found = _GITHUB.match(url)
    if not found:    # shortcut: GitHub only; read other hosts' raw files once plumb lives there
        return ""
    raw = f"https://raw.githubusercontent.com/{found[1]}/{found[2]}/main/{MANIFEST}"
    try:
        with urllib.request.urlopen(raw, timeout=TIMEOUT_S) as answer:   # noqa: S310 - https
            return str(json.loads(answer.read().decode("utf-8")).get("source_digest") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _latest(url: str) -> str:
    """The repository's digest, kept ``KEEP_S`` in plumb's home (a failure too)."""
    from plumb.launcher import plumb_home

    path = plumb_home() / "latest.json"
    kept = _read(path)
    if kept.get("url") == url and time.time() - float(kept.get("at") or 0) < KEEP_S:
        return str(kept.get("digest") or "")
    digest = _fetch(url)
    try:
        from plumb.understand.files import write_json_atomic

        write_json_atomic(path, {"url": url, "at": time.time(), "digest": digest})
    except OSError:
        pass
    return digest


def check(root: Path | str) -> dict[str, str]:
    """``{"state": "current" | "outdated" | "unchecked" | "", "running", "latest"}``: "" when
    no plugin runs this session; ``unchecked`` when the repository cannot be read (never red)."""
    loaded = _plugin(root)
    if not loaded:
        return {"state": "", "running": "", "latest": ""}
    running = str(_read(Path(loaded) / "vendor" / "MANIFEST.json").get("source_digest") or "")
    url = str(_read(Path(loaded) / ".claude-plugin" / "plugin.json").get("repository") or "")
    latest = _latest(url) if running and url else ""
    state = "unchecked" if not latest else "current" if latest == running else "outdated"
    return {"state": state, "running": running[:7], "latest": latest[:7]}


def outdated(root: Path | str) -> tuple[bool, str]:
    """``(True, "running <digest>, repository <digest>")`` when the loaded plugin differs from
    plumb's repository; ``(False, "")`` otherwise, unchecked included."""
    found = check(root)
    if found["state"] != "outdated":
        return False, ""
    return True, f"running {found['running']}, repository {found['latest']}"
