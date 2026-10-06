"""The host-neutral turn API (sp4 3.1, sp5 9): one ``handle_event`` for every host.

Every adapter (Claude Code, Codex, Pi, Hermes, the CLI-only fallback) turns its host's event
into a ``TurnEvent``, calls ``handle_event`` and renders the ``TurnOutput`` the way its host
can show it. This module delegates to the Claude Code handlers (the phase-0 delegation), so
every host gets the same records, deltas, cards and questions; only the rendering differs.

Self-recorded messages (R13 Q4): a prompt reaching ``handle_event`` from the CLI-only
fallback (``host == "cli"``, ``plumb turn start``) was recorded by the agent itself, not by a
host's prompt hook. Its prompt-log entry says ``via: turn``, so a confirmation resting on it
is labelled "self-recorded message" wherever it is shown.

Standard library only at import time: hooks start with minimal imports.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import TurnEvent, TurnOutput
from plumb.hosts.claude_code.hookio import (
    Deadline,
    HookContext,
    HookOutput,
    Kept,
    read_json,
    safe_session_id,
)
from plumb.hosts.claude_code.providers import LAZY

HOSTS = ("claude-code", "codex", "pi", "hermes", "cli")
SELF_RECORDING_HOSTS = ("cli",)  # the fallback: the agent records the owner's message itself
HOOK_NAMES = {"session-start": "session-start", "prompt": "prompt", "edit": "post-edit",
              "stop": "stop"}
DISPLAYS = ("owner", "unseen", "status")  # does the owner see the stop's owner_lines?
BUDGET_KEYS = {"session-start": "session_start", "prompt": "prompt", "edit": "post_edit",
               "stop": "stop"}


def via(event: TurnEvent) -> str:
    """How the prompt reached plumb: ``hook`` (the host's prompt hook) or ``turn`` (the
    agent ran ``plumb turn start``: a self-recorded message, R13 Q4)."""
    return "turn" if event.host in SELF_RECORDING_HOSTS else "hook"


def hook_data(event: TurnEvent) -> dict[str, Any]:
    """The Claude Code shaped input the delegated handlers read."""
    data: dict[str, Any] = {"session_id": event.session_id, "cwd": str(event.root),
                            "hook_event_name": event.kind}
    if event.kind == "prompt":
        data["prompt"] = event.text or ""
    elif event.kind == "edit" and event.path:
        data["tool_input"] = {"file_path": event.path}
    elif event.kind == "session-start" and event.source:
        data["source"] = event.source
    elif event.kind == "stop":
        data["stop_hook_active"] = bool(event.stop_active)
    return data


def event_from_data(kind: str, data: Mapping[str, Any], root: Path, host: str,
                    fmt: str = "claude") -> TurnEvent:
    """A ``TurnEvent`` from a host's stdin JSON: Claude Code's shape (``claude``, which
    Codex shares) or the ``TurnEvent`` fields directly (``json``)."""
    if kind not in HOOK_NAMES:
        raise ValueError(f"unknown event '{kind}'")

    def text(*keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str):
                return value
        return None

    path = text("path")
    tool_input = data.get("tool_input")
    if path is None and isinstance(tool_input, Mapping):
        raw = tool_input.get("file_path") or tool_input.get("notebook_path") \
            or tool_input.get("path")
        path = raw if isinstance(raw, str) else None
    stop_active = data.get("stop_active") if fmt == "json" else data.get("stop_hook_active")
    return TurnEvent(kind=kind, root=root,  # type: ignore[arg-type]
                     session_id=safe_session_id(text("session_id", "thread-id", "thread_id")),
                     host=host, text=text("text", "prompt"), path=path, source=text("source"),
                     stop_active=bool(stop_active))


def _budget_ms(root: Path, kind: str) -> float:
    from plumb.config import DEFAULT_HOOK_BUDGET_MS as defaults

    key = BUDGET_KEYS[kind]
    try:
        from plumb.config import load_config

        return float(load_config(root).hooks.budget_ms.get(key, defaults.get(key, 800)))
    except Exception:  # noqa: BLE001 - a broken config must not break the hook
        return float(defaults.get(key, 800))


def status_line(root: Path) -> str:
    """The one-line status card from ``.plumb/session/status.json`` (recomputes nothing)."""
    from plumb.hosts.claude_code.statusline import render

    return render(read_json(root / ".plumb" / "session" / "status.json"))


def _lines(text: str) -> tuple[str, ...]:
    return tuple(line for line in text.splitlines() if line.strip())


def to_turn_output(event: TurnEvent, out: HookOutput | None) -> TurnOutput:
    """Map a delegated handler's ``HookOutput`` to the host-neutral ``TurnOutput``."""
    out = out or HookOutput()
    agent: tuple[str, ...] = ()
    owner: tuple[str, ...] = ()
    block: str | None = None
    if event.kind in ("session-start", "prompt"):
        agent = _lines(out.text)
        owner = _lines(out.system_message)
    elif event.kind == "stop":
        owner = _lines(out.system_message or out.text)
        if out.block_reason and not event.stop_active:
            block = out.block_reason  # at most once per turn; never while continuing
    status = status_line(event.root) if event.kind in ("session-start", "stop") else ""
    return TurnOutput(agent_context=agent, owner_lines=owner, block=block, status_line=status)


def _handler(kind: str, verify: Any, backend: Any, unjudged: Any
             ) -> Callable[[HookContext], HookOutput | None]:
    if kind == "session-start":
        from plumb.hosts.claude_code import session_start

        return lambda ctx: session_start.handle(ctx, verify=verify)
    if kind == "prompt":
        from plumb.hosts.claude_code import prompt

        return lambda ctx: prompt.handle(ctx, verify=verify, backend=backend)
    if kind == "edit":
        from plumb.hosts.claude_code import post_edit

        return post_edit.handle
    from plumb.hosts.claude_code import stop

    return lambda ctx: stop.handle(ctx, verify=verify, unjudged=unjudged)


def handle_event(event: TurnEvent, *, deadline: Deadline | None = None,
                 kept: Kept | None = None, verify: Any = LAZY, backend: Any = LAZY,
                 unjudged: Any = LAZY, display: str = "owner") -> TurnOutput:
    """The one turn API. ``deadline`` and ``kept`` come from the hook runner when the event
    arrives through ``plumb hook``/``plumb turn`` (budget, watchdog, kept lines); tests pass
    fakes for ``verify``, ``backend`` and ``unjudged``.

    ``display`` says whether the owner sees this stop event's ``owner_lines`` (DISPLAYS):
    ``owner`` (the host shows them), ``unseen`` (it cannot: no record of the stated set is
    marked shown, so a bare "ok" relays none) or ``status`` (a status refresh that never
    rewrites the stated set). The stated set's one writer (``stop.write_stated``) applies it."""
    if event.kind not in HOOK_NAMES:
        raise ValueError(f"unknown event '{event.kind}'")
    if display not in DISPLAYS:
        raise ValueError(f"unknown display '{display}'")
    root = Path(event.root)
    ctx = HookContext(name=HOOK_NAMES[event.kind], data=hook_data(event), root=root,
                      session_id=safe_session_id(event.session_id),
                      deadline=deadline or Deadline(_budget_ms(root, event.kind)),
                      extra={"via": via(event), "host": event.host, "display": display})
    if kept is not None:
        ctx.kept = kept
    out = _handler(event.kind, verify, backend, unjudged)(ctx)
    return to_turn_output(event, out)


def as_json(output: TurnOutput) -> str:
    """``TurnOutput`` as one JSON object (``--format json``)."""
    return json.dumps({"agent_context": list(output.agent_context),
                       "owner_lines": list(output.owner_lines), "block": output.block,
                       "status_line": output.status_line}, ensure_ascii=False)
