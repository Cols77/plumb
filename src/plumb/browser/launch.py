"""The band's press on a new study opens the browser room on it (SR-294 EX-3, EX-4).

Only ``plumb mod room`` calls this, after the panel's key check, so the room never opens
without the owner's press (EX-2). The room's capability is derived from the panel's key, which
the agent never holds: a room this panel started answers it, any other room does not, and a
press then starts a new one. ``room.json`` in the session folder keeps the origin only."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from plumb import study
from plumb.understand import files

ROOM_FILE = "room.json"


def room_token(key: str) -> str:
    return hashlib.sha256(b"plumb-room:" + bytes.fromhex(key)).hexdigest()


def _alive(origin: str, token: str) -> bool:
    request = urllib.request.Request(origin + "/api/studies",
                                     headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=2) as answer:  # noqa: S310 - loopback
            return answer.status == 200
    except (OSError, ValueError):
        return False


def _start(root: Path, token: str) -> str:
    """``plumb ui`` on a free port, detached from this process (it outlives the press), the
    capability on its stdin; the origin it prints."""
    env = {**os.environ, "PLUMB_AGENT_SESSION": "", "PYTHONUTF8": "1"}
    flags: dict[str, Any] = ({"creationflags": subprocess.DETACHED_PROCESS
                              | subprocess.CREATE_NEW_PROCESS_GROUP}
                             if sys.platform == "win32" else {"start_new_session": True})
    child = subprocess.Popen(  # noqa: S603 - our own interpreter and module
        [sys.executable, "-m", "plumb", "ui", "--root", str(root), "--port", "0",
         "--token-stdin"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=env, text=True, **flags)
    assert child.stdin is not None and child.stdout is not None
    child.stdin.write(token + "\n")
    child.stdin.close()
    line = child.stdout.readline()      # "Plumb: http://127.0.0.1:<port>/#token=..."
    child.stdout.close()
    origin = line.partition("Plumb: ")[2].partition("/#")[0].strip()
    if not origin.startswith("http://127.0.0.1:"):
        raise OSError("the browser room did not start")
    return origin


def open_study(root: Path, session: str, key: str, slug: str) -> dict[str, Any]:
    """Open the room on ``slug`` (starting it when this panel's room is not running), then
    mark the study opened so the band's line goes."""
    study.get(root, slug)               # LookupError: no such study
    token = room_token(key)
    path = files.session_dir(root, session) / ROOM_FILE
    held = files.read_json(path)
    origin = str(held.get("origin") or "") if isinstance(held, dict) else ""
    if not origin or not _alive(origin, token):
        origin = _start(root, token)
        files.write_json_atomic(path, {"origin": origin})
    webbrowser.open(f"{origin}/?study={urllib.parse.quote(slug)}#token={token}")
    opened = study.mark(root, slug, "opened")
    return {"origin": origin, "slug": slug, "status": opened["status"]}

