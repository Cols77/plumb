"""The gate that holds a build until the owner answers (SHOW, spec 4.3).

``.plumb/session/<id>/gate`` says ``closed`` or ``open`` and names the owner message it is
about. The prompt hook closes it (``close``); only plumb opens it (``open``), each time with a
``gate`` entry in the log, so a file that reads open with no matching entry is reported
(``problems``): tamper-evident, not tamper-proof (SP7 5.7). Nothing here waits."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import GateState
from plumb.understand import files


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def state(root: Path, session: str) -> GateState:
    """The gate of the session; a session with no gate file is open."""
    return files.gate_from_json(files.read_json(files.gate_path(Path(root), session)))


def is_closed(root: Path, session: str) -> bool:
    return state(root, session).state == "closed"


def close(root: Path, session: str, digest: str, reason: str = "") -> GateState:
    """Close the gate for the owner message ``digest`` (the prompt hook's act)."""
    closed = GateState(state="closed", message_digest=digest, reason=reason, since=_now())
    files.write_json_atomic(files.gate_path(Path(root), session), files.gate_to_json(closed))
    return closed


def refresh(root: Path, session: str, digest: str, reason: str) -> bool:
    """Change the reason of a gate that is closed for exactly this message (a late result for
    an older message leaves the newer message's gate alone)."""
    current = state(root, session)
    if current.state != "closed" or current.message_digest != digest:
        return False
    files.write_json_atomic(files.gate_path(Path(root), session), files.gate_to_json(
        GateState(state="closed", message_digest=digest, reason=reason, since=current.since)))
    return True


def open(core: Any, session: str, digest: str, by: str, reason: str = "",  # noqa: A001
         proof: Mapping[str, Any] | None = None) -> bool:
    """Open the gate that is closed for the message ``digest``, with a ``gate`` log entry.

    Returns True when the gate is open for that message afterwards. A gate closed for a newer
    message stays closed (a late answer never opens a later message's gate); an open gate is
    left as it is and logs nothing. ``proof``: the typed message a release rests on."""
    root = Path(core.root)
    current = state(root, session)
    if current.state == "open":
        return True
    if digest != current.message_digest:
        return False
    core.log_append("events", "gate", {"digest": digest, "state": "open", "by": by,
                                       "reason": reason, **(proof or {})})
    files.write_json_atomic(files.gate_path(root, session), files.gate_to_json(GateState(
        state="open", message_digest=digest, reason=reason, since=_now())))
    return True


open_gate = open


def pending_digest(root: Path, session: str) -> str | None:
    """The message the gate is closed for, or None when it is open."""
    current = state(root, session)
    return current.message_digest if current.state == "closed" else None


def closed_reason(root: Path, session: str) -> str:
    return state(root, session).reason


def _opened(core: Any) -> set[str]:
    return {str(e.payload.get("digest")) for e in core.events()
            if e.kind == "gate" and e.payload.get("state") == "open"}


def problems(core: Any) -> list[str]:
    """Gate files that read open for a message with no ``gate`` entry opening it."""
    if core is None:
        return []
    folder = Path(core.root) / ".plumb" / "session"
    out: list[str] = []
    if not folder.is_dir():
        return out
    opened: set[str] | None = None
    for path in sorted(folder.glob("*/gate")):
        found = files.gate_from_json(files.read_json(path))
        if found.state != "open" or not found.message_digest:
            continue
        if opened is None:
            opened = _opened(core)
        if found.message_digest not in opened:
            out.append(f"the check before building is open in session {path.parent.name} "
                       "but the log has no record that plumb opened it")
    return out


# SR-196: the reason prefix of a gate the prompt hook closes on a request that changes a
# confirmed record while no intent loop ran for it; the owner's /plumb go releases it too
INTENT_CHANGE = "intent change:"

RELEASE_WORDS = {"typed": "the owner typed the release", "button": "the owner pressed Build anyway",
                 "owner-words": "the owner's words, read at the reader's threshold"}


def failed_check_open(root: Path, session: str) -> bool:
    """The gate is closed for a message whose check failed (its "couldn't check" card is
    still in the card store) or on an intent change (SR-196): the closures the owner may
    release."""
    from plumb.understand import cardstore

    current = state(Path(root), session)
    if current.state != "closed":
        return False
    if current.reason.startswith(INTENT_CHANGE):
        return True
    wanted = "couldnt_check:" + current.message_digest.removeprefix("sha256:")[:12]
    return any(c.id == wanted and c.status == "open"
               for c in cardstore.own_cards(Path(root), session))


def release(core: Any, session: str, via: str, *, digest: str = "") -> bool:
    """Open the gate of a failed check because the owner said so: ``via`` is ``typed`` (the
    caller checked the logged prompt is exactly ``/plumb go``), ``button`` or ``owner-words``
    (the caller checked the reader's answer is accepted at or above its threshold). No other
    route exists, and a gate closed by a card's questions is not released this way."""
    if via not in RELEASE_WORDS or not failed_check_open(Path(core.root), session):
        return False
    held = state(Path(core.root), session).message_digest
    note = RELEASE_WORDS[via] + (f" ({digest.removeprefix('sha256:')[:12]})" if digest else "")
    if not open(core, session, held, f"release:{via}", note,
                {"prompt_digest": digest} if digest else None):
        return False
    from plumb.understand import cardstore

    wanted = "couldnt_check:" + held.removeprefix("sha256:")[:12]
    cards = cardstore.own_cards(Path(core.root), session)
    cardstore.save(Path(core.root), session, [
        dataclasses.replace(c, status="closed") if c.id == wanted else c for c in cards])
    return True
