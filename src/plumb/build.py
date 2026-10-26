"""Which plumb build Claude Code runs, against plumb's local main and plumb's repository
(SR-357, SR-358). The running plugin is known by its vendored source digest and compared with
the one on the main of plumb's local clone (the session's repository when it is plumb's own). The
installed plugin is known by the commit Claude Code recorded, compared with the commit of the
main of the repository the plugin's ``plugin.json`` names (``git ls-remote``; a folder that is no
installed copy is compared as local main). Each misalignment is a line with both versions and the
fix; git history says which side is ahead. The remote is read by a detached process, never by
the hook, kept ``KEEP_S``; when it is unknown nothing is said against it but that.
Nothing is reinstalled or pushed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

MANIFEST = "plugin/vendor/MANIFEST.json"
KEEP_S = 900
REFRESH_S = 30.0      # the detached refresh may wait for the network; the hook never does
FAILED_S = 60.0       # a failed or running refresh is not started again for this long


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


def _installed(root: Path | str, loaded: str) -> str:
    """The commit Claude Code recorded when it installed the loaded plugin ("" for a folder
    that is no installed cache copy): the entry of this root's, else the user-wide one."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    entries = _read(home / "plugins" / "installed_plugins.json").get("plugins", {}).get(
        "plumb@plumb") or []

    def norm(path: object) -> str:
        return os.path.normcase(os.path.normpath(str(path)))
    here = [e for e in entries if isinstance(e, dict) and e.get("installPath")
            and norm(loaded).startswith(norm(e["installPath"]))] if loaded else []
    mine = [e for e in here if e.get("projectPath") and norm(e["projectPath"]) == norm(root)]
    anyone = [e for e in here if not e.get("projectPath")]
    return str(next(iter(mine or anyone), {}).get("gitCommitSha") or "")


def _fetch(url: str) -> str:
    """The commit of the repository's main; "" when it cannot be read."""
    try:
        done = subprocess.run(["git", "ls-remote", url, "refs/heads/main"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=REFRESH_S,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.SubprocessError):
        return ""
    head = done.stdout.split() if done.returncode == 0 else []
    return head[0] if head else ""


def _keep(url: str, commit: str, fresh_for: float) -> None:
    from plumb.launcher import plumb_home
    from plumb.understand.files import write_json_atomic

    try:
        write_json_atomic(plumb_home() / "latest.json", {
            "url": url, "commit": commit, "at": time.time() - KEEP_S + fresh_for})
    except OSError:
        pass


def _refresh(url: str) -> None:
    """Runs detached (``python -m plumb.build URL``): reads the remote, keeps the answer
    ``KEEP_S``, or a failure ``FAILED_S``."""
    commit = _fetch(url)
    _keep(url, commit, KEEP_S if commit else FAILED_S)


def _spawn(url: str) -> None:
    flags = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
             if os.name == "nt" else {"start_new_session": True})
    try:
        subprocess.Popen([sys.executable, "-m", "plumb.build", url], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    except OSError:
        pass


def _latest(url: str) -> str:
    """The repository main's commit as last kept in plumb's home; never waits for the network:
    a stale or missing answer is returned as it is ("" when none) and a detached process
    refreshes it, once per ``FAILED_S`` at most."""
    from plumb.launcher import plumb_home

    kept = _read(plumb_home() / "latest.json")
    same = kept.get("url") == url
    if not same or time.time() - float(kept.get("at") or 0) >= KEEP_S:
        _keep(url, str(kept.get("commit") or "") if same else "", FAILED_S)   # the lease
        _spawn(url)
    return str(kept.get("commit") or "") if same else ""


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
    commit = _latest(url) if url else ""
    installed = _installed(root, loaded)
    head = (_git(clone, "rev-parse", "main") or "").strip() if local else ""
    name, ours = ("installed plugin", installed) if installed else ("local main", head)
    if commit and ours and ours != commit:
        # shortcut: without a local clone there is no history to order them; say "differs"
        way = _way(clone, ours, commit) if clone else "differs"
        how = {"behind": "is behind", "ahead": "is ahead of", "differs": "differs from"}[way]
        fix = {"behind": "update the plugin, then reload plugins" if installed else "pull main",
               "ahead": "push main",
               "differs": "update the plugin, then reload plugins" if installed else
               "pull or push main"}[way]
        lines.append(f"{name} {ours[:7]} {how} its repository's {commit[:7]}: {fix}")
    return {"lines": lines, "unchecked": not commit, "loaded": True}


def outdated(root: Path | str) -> tuple[bool, str]:
    """``(True, "<the first misalignment>")`` when the running plugin is not the build it should
    be (local main's, else the repository's); ``(False, "")`` otherwise."""
    lines = check(root)["lines"]
    first = next((line for line in lines if line.startswith(("plumb ", "installed plugin "))), "")
    return (True, first) if first else (False, "")


if __name__ == "__main__":
    _refresh(sys.argv[1])
