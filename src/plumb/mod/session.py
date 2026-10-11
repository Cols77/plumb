"""The mod's registration for a session and the key check (sp7-owner-surface 5.1, DEC-025).

The mod makes a 32-byte random key at session start and keeps it in its own state. It registers
only the key's digest: ``key_digest`` is the lowercase sha256 hex of the 32 key bytes (the key
travels as 64 hex characters, on stdin only). ``mod.json`` is written once per session, with an
exclusive create, so the first registration wins and a key registered after the mod is useless.
The registration is also logged (``mod-hello``: session and digest, never the key), so a button
approval can be re-checked from the committed log where the session folder does not exist."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.understand import files

HELLO_KIND = "mod-hello"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Refused(PermissionError):
    """Refused (exit 3): nothing was written."""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def mod_path(root: Path, session: str) -> Path:
    return files.session_dir(root, session) / "mod.json"


def key_digest(key: str) -> str:
    """The digest the mod registers for ``key`` (64 hex characters): sha256 hex of its bytes."""
    return hashlib.sha256(bytes.fromhex(key)).hexdigest()


def refuse_under_marker(command: str) -> None:
    """The agent's shell never runs the mod's commands: the mod runs them with the session
    marker removed, so a marker means an agent (SR-086 EX-3)."""
    from plumb.approvals import marker

    if marker():
        raise Refused(f"plumb mod {command} refused: only plumb's panel runs it, never the "
                      "agent's shell")


def read_stdin_json(stream: Any) -> Mapping[str, Any]:
    """The JSON object on stdin, or an empty mapping (a missing or broken input refuses)."""
    try:
        data = json.loads(stream.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, Mapping) else {}


def registration(root: Path, session: str) -> Mapping[str, Any] | None:
    data = files.read_json(mod_path(root, session))
    return data if isinstance(data, Mapping) else None


def hello(core: Any, session: str, digest: Any) -> Mapping[str, Any]:
    """Register ``digest`` for ``session``: writes ``mod.json`` ``{active, since, key_digest,
    heartbeat}`` and logs ``mod-hello``. A second registration of the session is refused."""
    refuse_under_marker("hello")
    if not session.strip():
        raise Refused("plumb mod hello refused: no session")
    if not isinstance(digest, str) or not _HEX64.match(digest):
        raise Refused("plumb mod hello refused: no key digest (64 hex characters) on stdin")
    path = mod_path(core.root, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now()
    data = {"active": True, "since": stamp, "key_digest": digest, "heartbeat": stamp}
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise Refused("plumb mod hello refused: this session already has its panel") from exc
    with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(data, sort_keys=True, indent=1) + "\n")
    core.log_append("events", HELLO_KIND, {"session": session, "key_digest": digest,
                                           "since": stamp})
    return data


def check_key(root: Path, session: str, payload: Mapping[str, Any], command: str) -> str:
    """The registered digest when ``payload["key"]`` is the session's key; else ``Refused``
    (the marker is set, no ``mod.json``, no key, a malformed key, or another key)."""
    refuse_under_marker(command)
    held = registration(root, session)
    registered = held.get("key_digest") if held is not None else None
    if not isinstance(registered, str) or not registered:
        raise Refused(f"plumb mod {command} refused: no panel is registered for this session")
    key = payload.get("key")
    if not isinstance(key, str) or not _HEX64.match(key.lower()):
        raise Refused(f"plumb mod {command} refused: no key on stdin")
    digest = key_digest(key.lower())
    if not hmac.compare_digest(digest, registered):
        raise Refused(f"plumb mod {command} refused: the key is not this session's")
    return digest


def logged_digest(events: Any, session: str) -> str | None:
    """The key digest the session's first ``mod-hello`` entry registered (written with no
    marker), or None."""
    for entry in events:
        if entry.kind == HELLO_KIND and entry.payload.get("session") == session \
                and entry.marker == "none":
            digest = entry.payload.get("key_digest")
            return str(digest) if digest else None
    return None
