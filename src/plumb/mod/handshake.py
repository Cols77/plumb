"""The command hooks' side of the handshake with plumb's panel (sp7-owner-surface 5.1, DEC-024;
sp7-realign-sp8 C7).

The panel (the Claude Code mod) registers with ``plumb mod hello`` and then refreshes the
``heartbeat`` of ``.plumb/session/<id>/mod.json`` at the start of every turn. The command hooks
read that one small file:

- ``stop``: while the panel is active (``active``: registered, not marked off, its heartbeat not
  older than the turn's start), the owner's part of the stop hook goes to
  ``.plumb/session/<id>/present.json`` (``{turn, confirmations, cards}``; each card with its
  full content, SR-116) and no
  ``systemMessage`` is printed (``deliver``).
  A block (the instruction to the agent) is unchanged. Otherwise the hook prints as before.
- ``session-start``: first of all, before any step its budget can cut (SR-125), writes
  ``host.json`` (the interpreter that runs plumb, so the panel can run ``plumb mod`` with the
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

from plumb.understand import files

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
    """``host.json``: the interpreter running plumb, which the panel runs ``plumb mod`` with
    (it cannot read the plugin's data folder from its own environment)."""
    try:
        files.write_json_atomic(_session_file(root, session, "host.json"), {
            "python": sys.executable, "plumb_home": os.environ.get("PLUMB_HOME", ""),
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
        from plumb.mod.session import retire

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


def awaiting_cards(core: Any, session: str, stamp: int) -> list[Any]:
    """The cards that ask the owner at the end of this turn, as the text summary orders them:
    the awaiting ones, then a "couldn't check" card per failed job."""
    from plumb.understand import cards as card_text
    from plumb.understand import cardstore, summary

    held = cardstore.states(core, session)
    cards = [c for c in cardstore.load(core.root, session)
             if held.get(c.id, ("",))[0] != "processing"]
    try:
        cards.extend(summary._failure_cards(core, session))
    except Exception:  # noqa: BLE001 - a card that cannot be made is left out
        pass
    return sorted(cards, key=card_text.kind_rank)


def present_cards(core: Any, session: str, stamp: int) -> list[dict[str, Any]]:
    """The cards of ``present.json``: the ones the end-of-turn text drew (``summary.read_drawn``,
    slice 3's full cards), each as ``cards.json`` holds a card plus its full content (SR-116,
    ``understand.fullcard``); without that record, the awaiting cards with their content."""
    from plumb.mod.offers import content_for
    from plumb.understand import cardstore, summary

    drawn = [e for e in summary.read_drawn(core.root, session)
             if e["card"].get("status") != "left_open"]
    if drawn:
        return [{**dict(e["card"]), "content": e.get("content")} for e in drawn]
    return [{**cardstore.card_to_json(c), "content": content_for(core, session, c)}
            for c in awaiting_cards(core, session, stamp)]


def write_present(ctx: Any, turn: Mapping[str, Any]) -> dict[str, Any]:
    """Write ``present.json`` for this turn: the parts the stop hook kept for the owner
    (``ctx.extra["stop_parts"]``), and the cards it drew in full."""
    from plumb.api import open_core

    core = open_core(ctx.root)
    started = _turn_start(turn)
    parts = ctx.extra.get("stop_parts")
    data = {"turn": int(started), "confirmations": list(getattr(parts, "confirmations", ()) or ()),
            "session": ctx.session_id, "cards": present_cards(core, ctx.session_id, int(started)),
            "turn_id": str(turn.get("turn_id") or ""),
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    files.write_json_atomic(present_path(ctx.root, ctx.session_id), data)
    return data


def deliver(ctx: Any, output: Any) -> Any:
    """The stop hook's answer: unchanged without an active panel or for a block; otherwise
    ``present.json`` is written and no ``systemMessage`` is printed. Any failure here prints
    as before."""
    if output is not None and getattr(output, "block_reason", ""):
        return output
    try:
        turn = _turn(ctx)
        if not active(ctx.root, ctx.session_id, _turn_start(turn)):
            return output
        before = files.read_json(present_path(ctx.root, ctx.session_id))
        data = write_present(ctx, turn)
        line = turn_line(ctx, before, data)
    except Exception:  # noqa: BLE001 - the owner's summary is never lost to the panel
        return output
    if line:
        from plumb.hosts.claude_code.hookio import HookOutput

        return HookOutput(system_message=line)
    return None


def turn_line(ctx: Any, before: Any, data: Mapping[str, Any]) -> str:
    """SR-159: the one plumb line for a turn end with the panel running: new cards waiting,
    answers applied (by the card's title), nothing when neither changed. Plain text: a hook's
    ``systemMessage`` cannot carry colour. ``turnline.json`` holds each card's state seen at
    the last turn end."""
    from plumb.api import open_core
    from plumb.understand import cardstore, summary

    core = open_core(ctx.root)
    seen_path = _session_file(ctx.root, ctx.session_id, "turnline.json")
    seen = files.read_json(seen_path)
    seen = seen if isinstance(seen, Mapping) else {}
    states = {k: v[0] for k, v in cardstore.states(core, ctx.session_id).items()}
    files.write_json_atomic(seen_path, states)
    old = {str(c.get("id")) for c in (before or {}).get("cards", ()) if isinstance(c, Mapping)}
    fresh = [c for c in data.get("cards", ()) if c.get("id") not in old]
    titles = {c.id: c.topic for c in cardstore.load(core.root, ctx.session_id, open_only=False)}
    titles.update({str(e["card"].get("id")): str(e["card"].get("topic"))
                   for e in summary.read_drawn(ctx.root, ctx.session_id)})
    applied = [titles.get(k, k) for k, v in states.items()
               if v == "done" and seen.get(k) in ("waiting", "processing")]
    lines = [f"plumb: your answer on {t} was applied" for t in applied]
    if fresh:
        lines.append("plumb: 1 new card waits on the panel" if len(fresh) == 1
                     else f"plumb: {len(fresh)} new cards wait on the panel")
    return "\n".join(lines)
