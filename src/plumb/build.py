"""Which plumb build Claude Code runs, against plumb's local main and plumb's repository
(SR-357, SR-358). Three builds, each known by its vendored source digest: the loaded plugin's,
the one on the main of plumb's local clone (the session's repository when it is plumb's own), and
the one on the main of the repository the plugin's ``plugin.json`` names. Each misalignment is a
line with both versions and the fix; git history says which side is ahead. The repository is read
at most once per ``KEEP_S``, and when it cannot be read nothing is said against it but that.
Nothing is reinstalled or pushed."""

from __future__ import annotations

import json
import os
import re
import subprocess
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


def _digest(text: str | None) -> str:
    try:
        return str(json.loads(text or "").get("source_digest") or "")
    except (ValueError, AttributeError):
        return ""


def _git(root: Path | str, *args: str, timeout: float = 2.0) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
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
    return str(_read(host).get("plugin") or "")


def _fetch(url: str) -> tuple[str, str]:
    """``(digest, commit)`` of the repository's main; "" for what cannot be read."""
    import urllib.request

    found = _GITHUB.match(url)
    if not found:    # shortcut: GitHub only; read other hosts' raw files once plumb lives there
        return "", ""
    raw = f"https://raw.githubusercontent.com/{found[1]}/{found[2]}/main/{MANIFEST}"
    try:
        with urllib.request.urlopen(raw, timeout=TIMEOUT_S) as answer:   # noqa: S310 - https
            digest = _digest(answer.read().decode("utf-8"))
    except (OSError, ValueError):
        return "", ""
    head = (_git(".", "ls-remote", url, "refs/heads/main", timeout=TIMEOUT_S) or "").split()
    return digest, head[0] if head else ""


def _latest(url: str) -> tuple[str, str]:
    """The repository's ``(digest, commit)``, kept ``KEEP_S`` in plumb's home (a failure too)."""
    from plumb.launcher import plumb_home

    path = plumb_home() / "latest.json"
    kept = _read(path)
    if kept.get("url") == url and time.time() - float(kept.get("at") or 0) < KEEP_S:
        return str(kept.get("digest") or ""), str(kept.get("commit") or "")
    digest, commit = _fetch(url)
    try:
        from plumb.understand.files import write_json_atomic

        write_json_atomic(path, {"url": url, "at": time.time(), "digest": digest,
                                 "commit": commit})
    except OSError:
        pass
    return digest, commit


def _built_at(clone: str, digest: str) -> str:
    """The commit of ``clone`` whose build is ``digest``, the first one; "" when none is."""
    found = (_git(clone, "log", "--all", "--reverse", "--format=%H", f"-S{digest}", "--",
                  MANIFEST) or "").split()
    return next((c for c in found if digest in (_git(clone, "show", f"{c}:{MANIFEST}") or "")),
                "")


def _way(clone: str, ours: str, theirs: str) -> str:
    """``behind``, ``ahead`` or ``differs``: ``ours`` against ``theirs`` in ``clone``'s history."""
    if clone and ours and theirs:
        if _git(clone, "merge-base", "--is-ancestor", ours, theirs) is not None:
            return "behind"
        if _git(clone, "merge-base", "--is-ancestor", theirs, ours) is not None:
            return "ahead"
    return "differs"


def check(root: Path | str) -> dict:
    """``{"lines": [...], "unchecked": bool, "loaded": bool}``: one line per misalignment of
    the running plugin, plumb's local main and plumb's repository main."""
    loaded = _plugin(root)
    running = str(_read(Path(loaded) / "vendor" / "MANIFEST.json").get("source_digest") or "") \
        if loaded else ""
    if not running:
        return {"lines": [], "unchecked": False, "loaded": False}
    clone = str(root) if _git(root, "cat-file", "-e", f"main:{MANIFEST}") is not None else ""
    local = _digest(_git(clone, "show", f"main:{MANIFEST}")) if clone else ""
    lines = []
    if local and local != running:
        way = _way(clone, _built_at(clone, running), _built_at(clone, local))
        lines.append({
            "behind": f"plumb {running[:7]} is behind local main's {local[:7]}: reload plugins",
            "ahead": f"plumb {running[:7]} is ahead of local main's {local[:7]} (built from "
                     "another branch)",
            "differs": f"plumb {running[:7]} differs from local main's {local[:7]}: reload "
                       "plugins"}[way])
    url = str(_read(Path(loaded) / ".claude-plugin" / "plugin.json").get("repository") or "")
    latest, commit = _latest(url) if url else ("", "")
    name, ours = ("local main", local) if local else ("plumb", running)
    if latest and latest != ours:
        # shortcut: without a local clone there is no history to order them; say "differs"
        way = _way(clone, (_git(clone, "rev-parse", "main") or "").strip(), commit) \
            if local else "differs"
        how = {"behind": "is behind", "ahead": "is ahead of", "differs": "differs from"}[way]
        fix = {"behind": "pull main", "ahead": "push main",
               "differs": "pull or push main" if local else
               "update the plugin, then reload plugins"}[way]
        lines.append(f"{name} {ours[:7]} {how} its repository's {latest[:7]}: {fix}")
    return {"lines": lines, "unchecked": not latest, "loaded": True}


def outdated(root: Path | str) -> tuple[bool, str]:
    """``(True, "<the first misalignment>")`` when the running plugin is not the build it should
    be (local main's, else the repository's); ``(False, "")`` otherwise."""
    lines = check(root)["lines"]
    first = next((line for line in lines if line.startswith("plumb ")), "")
    return (True, first) if first else (False, "")
