"""The command hooks' side of the handshake with iaso's panel (sp7-owner-surface 5.1, DEC-024;
sp7-realign-sp8 C7).

The panel (the Claude Code mod) registers with ``iaso mod hello`` and then refreshes the
``heartbeat`` of ``.iaso/session/<id>/mod.json`` at the start of every turn. The command hooks
read that one small file:

- ``stop``: while the panel is active (``active``: registered, not marked off, its heartbeat not
  older than the turn's start), the owner's part of the stop hook goes to
  ``.iaso/session/<id>/present.json`` (``{turn, confirmations}``) and no
  ``systemMessage`` but the one owner line is printed (``deliver``).
  A block (the instruction to the agent) is unchanged. Otherwise the hook prints as before.
- ``session-start``: first of all, before any step its budget can cut (SR-125), writes
  ``host.json`` (the interpreter that runs iaso, so the panel can run ``iaso mod`` with the
  same one) and ``brief.json`` (``{injected: true}``): the agent gets the brief with the panel
  up or not (SR-173).

Nothing here fails a hook: a file that cannot be read means the panel is not active."""

from __future__ import annotations

import calendar
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from iaso.understand import files

# the panel writes its heartbeat on its own ``turn.start``, which the host may raise a moment
# before the prompt hook stamps ``turn_start``: a heartbeat this close before it still counts
HEARTBEAT_SLACK_S = 10.0


def _session_file(root: Path, session: str, name: str) -> Path:
    return files.session_dir(root, session) / name


def present_path(root: Path, session: str) -> Path:
    return _session_file(root, session, "present.json")


def _epoch(stamp: Any) -> float | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return float(calendar.timegm(time.strptime(stamp, fmt)))
        except ValueError:
            continue
    return None


def registration(root: Path, session: str) -> Mapping[str, Any] | None:
    data = files.read_json(_session_file(root, session, "mod.json"))
    return data if isinstance(data, Mapping) else None


def active(root: Path, session: str, turn_start: float) -> bool:
    """True when the panel registered for ``session``, is not marked off (``active: false``,
    its fallback) and refreshed its heartbeat for this turn (at or after ``turn_start``, less
    ``HEARTBEAT_SLACK_S``). Without a turn start, a registered panel is active."""
    held = registration(root, session)
    if held is None or held.get("active") is not True:
        return False
    if turn_start <= 0:
        return True
    beat = _epoch(held.get("heartbeat"))
    return beat is not None and beat >= turn_start - HEARTBEAT_SLACK_S


def background_owned(root: Path, session: str) -> bool:
    """True when the panel says it gives the model the session background itself (its
    ``prompt.compose`` section); the session-start hook then leaves the brief out."""
    held = registration(root, session)
    return held is not None and held.get("active") is True and held.get("background") is True


def write_host(root: Path, session: str) -> None:
    """``host.json``: the interpreter running iaso, which the panel runs ``iaso mod`` with
    (it cannot read the plugin's data folder from its own environment), and the plugin folder
    this session loaded (SR-356: which build ``iaso debug done`` runs beside)."""
    try:
        files.write_json_atomic(_session_file(root, session, "host.json"), {
            "python": sys.executable, "iaso_home": os.environ.get("IASO_HOME", ""),
            "plugin": os.environ.get("CLAUDE_PLUGIN_ROOT")
            or os.environ.get("IASO_PLUGIN_ROOT", ""),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    except OSError:
        pass


def record_brief(root: Path, session: str, injected: bool) -> None:
    try:
        files.write_json_atomic(_session_file(root, session, "brief.json"),
                                {"injected": injected})
    except OSError:
        pass


def session_start(ctx: Any) -> None:
    """The session-start hook's first step (see the module doc): ``host.json``; on a resumed
    session the registration of the panel that ran before is retired (its process and key are
    gone: the new panel registers again); then ``brief.json`` records that the brief goes in
    (SR-173: the agent always gets it, panel or not)."""
    write_host(ctx.root, ctx.session_id)
    data = getattr(ctx, "data", None)
    if isinstance(data, Mapping) and data.get("source") == "resume":
        from iaso.mod.session import retire

        retire(ctx.root, ctx.session_id)
    record_brief(ctx.root, ctx.session_id, True)


# --------------------------------------------------------------------------- stop


def _turn(ctx: Any) -> Mapping[str, Any]:
    data = files.read_json(_session_file(ctx.root, ctx.session_id, "turn.json"))
    return data if isinstance(data, Mapping) else {}


def _turn_start(turn: Mapping[str, Any]) -> float:
    try:
        return float(turn.get("turn_start") or 0)
    except (TypeError, ValueError):
        return 0.0


def write_present(ctx: Any, turn: Mapping[str, Any]) -> dict[str, Any]:
    """Write ``present.json`` for this turn: the parts the stop hook kept for the owner
    (``ctx.extra["stop_parts"]``)."""
    started = _turn_start(turn)
    parts = ctx.extra.get("stop_parts")
    from iaso.present.owner_text import JUDGE_APPROVED

    # SR-251: the band's status counts judge approvals; no line of the band for them alone
    said = [c for c in getattr(parts, "confirmations", ()) or () if not c.endswith(JUDGE_APPROVED)]
    data = {"turn": int(started), "confirmations": said,
            "session": ctx.session_id,
            "turn_id": str(turn.get("turn_id") or ""),
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    files.write_json_atomic(present_path(ctx.root, ctx.session_id), data)
    return data


def deliver(ctx: Any, output: Any) -> Any:
    """The stop hook's answer: unchanged without an active panel or for a block; otherwise
    ``present.json`` is written too; the stop's one owner line (SR-265) is printed either
    way. Any failure here prints as before."""
    if output is not None and getattr(output, "block_reason", ""):
        return output
    try:
        turn = _turn(ctx)
        if active(ctx.root, ctx.session_id, _turn_start(turn)):
            write_present(ctx, turn)
    except Exception:  # noqa: BLE001 - the owner's line is never lost to the panel
        pass
    return output
