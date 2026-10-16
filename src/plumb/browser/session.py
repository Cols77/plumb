"""Separate browser registrations; keys remain in the server's memory."""

import hmac
from pathlib import Path

from plumb.mod.session import Refused, accepted_digests, key_digest, now, refuse_under_marker
from plumb.understand import files


def registration(root: Path, session: str):
    data = files.read_json(files.session_dir(root, session) / "browser.json")
    return data if isinstance(data, dict) else None


def hello(core, session: str, key: str):
    refuse_under_marker("browser startup")
    digest = key_digest(key)
    held = registration(core.root, session)
    data = {
        "surface": "browser",
        "key_digest": digest,
        "since": now(),
        "earlier": [d for d in accepted_digests(held) if d != digest],
    }
    files.write_json_atomic(files.session_dir(core.root, session) / "browser.json", data)
    core.log_append("events", "browser-hello", {"session": session, **data})
    return digest


def check_key(root, session, payload, command):
    refuse_under_marker(command)
    held = registration(root, session)
    try:
        digest = key_digest(payload["key"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Refused("browser key missing or malformed") from exc
    if not held or not hmac.compare_digest(digest, str(held.get("key_digest") or "")):
        raise Refused("browser key does not match this session")
    return digest
