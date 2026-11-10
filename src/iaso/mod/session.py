"""The mod's registration for a session and the key check (sp7-owner-surface 5.1, DEC-025).

The mod makes a 32-byte random key at session start and keeps it in its own state. It registers
only the key's digest: ``key_digest`` is the lowercase sha256 hex of the 32 key bytes (the key
travels as 64 hex characters, on stdin only). ``mod.json`` is written once per session, with an
exclusive create, so the first registration wins and a key registered after the mod is useless.
A resumed session (``claude --resume``: the same session id, a new panel process with a new key)
is the one exception: its session-start hook, run by Claude Code and never under the agent's
marker, marks the registration ``retired`` (``retire``), and the new panel's hello then
replaces it, keeping the digests it held before under ``earlier`` so the approvals pressed
with them still re-check. The registration is also logged (``mod-hello``: session and digest,
never the key), so a button approval can be re-checked from the committed log where the session
folder does not exist."""

from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.understand import files

HELLO_KIND = "mod-hello"
SILENT_S = 60  # a registration with no heartbeat for this long may be taken over
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
    from iaso.approvals import marker

    if marker():
        raise Refused(f"iaso mod {command} refused: only iaso's panel runs it, never the "
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


def retire(root: Path, session: str) -> bool:
    """A resumed session's start: the registration of the panel that ran before (its process
    and key are gone) is marked ``retired`` and inactive, so the new panel's hello replaces it
    and the hooks stop counting on it. Only the session-start hook calls this (no command
    reaches it), and a resumed session's hook inherits the agent marker the first start
    exported into the session env, so the marker is not checked. True when retired."""
    held = registration(root, session)
    if held is None or held.get("retired"):
        return False
    try:
        files.write_json_atomic(mod_path(root, session),
                                {**held, "active": False, "retired": now()})
    except OSError:
        return False
    return True


def accepted_digests(held: Mapping[str, Any] | None) -> tuple[str, ...]:
    """The key digests a registration answers for: the current one, then the ones it replaced
    on a resume (approvals pressed with those still re-check)."""
    if held is None:
        return ()
    earlier = held.get("earlier")
    found = [held.get("key_digest"), *(earlier if isinstance(earlier, list) else ())]
    return tuple(str(d) for d in found if isinstance(d, str) and d)


def hello(core: Any, session: str, digest: Any) -> Mapping[str, Any]:
    """Register ``digest`` for ``session``: writes ``mod.json`` ``{active, since, key_digest,
    heartbeat}`` and logs ``mod-hello``. A second registration of the session is refused, unless
    the session's start retired the first one (a resumed session, ``retire``) or its heartbeat
    is older than ``SILENT_S`` (a panel restarted by a plugin reload)."""
    refuse_under_marker("hello")
    if not session.strip():
        raise Refused("iaso mod hello refused: no session")
    if not isinstance(digest, str) or not _HEX64.match(digest):
        raise Refused("iaso mod hello refused: no key digest (64 hex characters) on stdin")
    path = mod_path(core.root, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now()
    data = {"active": True, "since": stamp, "key_digest": digest, "heartbeat": stamp}
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        held = registration(core.root, session)
        if held is None or not (held.get("retired") or _silent(held)):
            raise Refused("iaso mod hello refused: this session already has its panel") from exc
        return _replace(core, session, digest, held)
    with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(data, sort_keys=True, indent=1) + "\n")
    core.log_append("events", HELLO_KIND, {"session": session, "key_digest": digest,
                                           "since": stamp})
    return data


def _silent(held: Mapping[str, Any]) -> bool:
    try:
        beat = calendar.timegm(time.strptime(str(held.get("heartbeat")), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return True
    return time.time() - beat > SILENT_S


def _replace(core: Any, session: str, digest: str, held: Mapping[str, Any]
             ) -> Mapping[str, Any]:
    """The hello of a resumed or reloaded session's new panel: its digest replaces the old one."""
    stamp = now()
    earlier = [d for d in accepted_digests(held) if d != digest]
    data = {"active": True, "since": stamp, "key_digest": digest, "heartbeat": stamp,
            "earlier": earlier}
    files.write_json_atomic(mod_path(core.root, session), data)
    core.log_append("events", HELLO_KIND, {"session": session, "key_digest": digest,
                                           "since": stamp, "replaces": earlier[:1]})
    return data


def check_key(root: Path, session: str, payload: Mapping[str, Any], command: str) -> str:
    """The registered digest when ``payload["key"]`` is the session's key; else ``Refused``
    (the marker is set, no ``mod.json``, no key, a malformed key, or another key)."""
    refuse_under_marker(command)
    held = registration(root, session)
    registered = held.get("key_digest") if held is not None else None
    if not isinstance(registered, str) or not registered:
        raise Refused(f"iaso mod {command} refused: no panel is registered for this session")
    key = payload.get("key")
    if not isinstance(key, str) or not _HEX64.match(key.lower()):
        raise Refused(f"iaso mod {command} refused: no key on stdin")
    digest = key_digest(key.lower())
    if not hmac.compare_digest(digest, registered):
        raise Refused(f"iaso mod {command} refused: the key is not this session's")
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
