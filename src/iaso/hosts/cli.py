"""``iaso hosts``, ``iaso turn`` and ``iaso hook <event> --host X --format F`` (sp4 3, 4).

- ``iaso turn start`` / ``iaso turn end``: the CLI-only fallback every host keeps. The agent
  runs them at the start of a task and before its final reply; they are the ``prompt`` and
  ``stop`` events of ``iaso.hosts.neutral.handle_event`` (the first ``turn start`` of a
  session also gives the session brief). Both always exit 0.
- ``iaso hook <event> --host X [--format claude|json|text] [--notify]``: a host's hook
  entry point. It builds the ``TurnEvent`` from stdin (Claude Code's shape, which Codex
  shares, by default; the ``TurnEvent`` fields with ``--format json``), calls
  ``handle_event`` within the sp1 budgets and the watchdog, and prints the ``TurnOutput`` in
  the requested format. ``--notify`` takes the JSON from the last argument instead of stdin
  (Codex's ``notify`` program), never blocks and never rewrites the stated set (a status
  refresh: the owner does not see its output). ``--unseen`` says the host could not show
  the owner this stop's ``owner_lines``, so no stated record is marked shown. Always exits 0.
- ``iaso hosts install|uninstall|status <host>``: the thin adapters for ``codex``
  and ``hermes``.

Imports stay light: hooks call this every turn.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

FORMATS = ("claude", "json", "text")
EVENTS = {"session-start": "session-start", "prompt": "prompt", "post-edit": "edit",
          "edit": "edit", "stop": "stop"}
CLAUDE_EVENT = {"session-start": "SessionStart", "prompt": "UserPromptSubmit",
                "edit": "PostToolUse", "stop": "Stop"}
ADAPTERS = {"codex": "iaso.hosts.codex.install",
            "hermes": "iaso.hosts.hermes.install"}

_HOOK_USAGE = ("usage: iaso hook {session-start|prompt|post-edit|stop} --host HOST "
               "[--format claude|json|text] [--notify] [--unseen] [--root PATH]\n")
_TURN_USAGE = ("usage: iaso turn {start|end} [--session ID] [--prompt-file F] "
               "[--format text|json] [--root PATH]\n"
               "The CLI-only fallback: `turn start` (the owner's message on stdin or in "
               "--prompt-file) logs the prompt digest and prints the relevant records; `turn "
               "end` prints the summary and, when the work must go on, one instruction. Both "
               "exit 0.\n")
_HOSTS_USAGE = ("usage: iaso hosts {install|uninstall|status} [codex|hermes] "
                "[--dry-run] [--launcher auto|path|venv|uv] [--root PATH]\n")


# --------------------------------------------------------------------------- rendering


class Rendered:
    """A ``TurnOutput`` rendered for one host format (what ``run_hook`` prints)."""

    def __init__(self, kind: str, output: Any, fmt: str) -> None:
        self.kind, self.output, self.fmt = kind, output, fmt

    def render(self) -> str:
        out = self.output
        if self.fmt == "json":
            from iaso.hosts.neutral import as_json

            return as_json(out)
        if self.fmt == "text":
            lines = [*out.agent_context, *out.owner_lines]
            if out.block:
                lines.append(out.block)
            return "\n".join(lines)
        return render_claude(self.kind, out)


def render_claude(kind: str, out: Any) -> str:
    """Claude Code's hook wire in its JSON form, which Codex's hooks accept as well."""
    data: dict[str, Any] = {}
    if kind in ("session-start", "prompt") and out.agent_context:
        data["hookSpecificOutput"] = {"hookEventName": CLAUDE_EVENT[kind],
                                      "additionalContext": "\n".join(out.agent_context)}
    if kind == "stop" and out.block:
        return json.dumps({"decision": "block", "reason": out.block}, ensure_ascii=False)
    if out.owner_lines:
        data["systemMessage"] = "\n".join(out.owner_lines)
    return json.dumps(data, ensure_ascii=False) if data else ""


# --------------------------------------------------------------------------- running


def _options(argv: list[str], flags: tuple[str, ...], values: tuple[str, ...]
             ) -> tuple[dict[str, Any], list[str]]:
    opts: dict[str, Any] = {}
    rest: list[str] = []
    it = iter(argv)
    for arg in it:
        name, eq, value = arg.partition("=")
        if name in values:
            opts[name] = value if eq else next(it, None)
        elif arg in flags:
            opts[arg] = True
        else:
            rest.append(arg)
    return opts, rest


def run_event(kind: str, data: dict[str, Any], *, host: str, fmt: str,
              root: str | None, stdout: Any = None, start: float | None = None,
              display: str = "owner") -> int:
    """One event through ``handle_event`` inside the hook runner (budget, watchdog, kept
    lines, the catch-all). ``display``: see ``handle_event``. Always returns 0."""
    from iaso.hosts.claude_code.hookio import hook_budget, run_hook, use_utf8_stdio
    from iaso.hosts.neutral import BUDGET_KEYS, event_from_data, handle_event

    if stdout is None:
        use_utf8_stdio()

    def handler(ctx: Any) -> Rendered:
        event = event_from_data(kind, ctx.data, ctx.root, host, fmt)
        return Rendered(kind, handle_event(event, deadline=ctx.deadline, kept=ctx.kept,
                                           display=display), fmt)

    return run_hook(EVENTS.get(kind, kind), handler,
                    stdin=io.StringIO(json.dumps(data)),
                    stdout=sys.stdout if stdout is None else stdout, root=root,
                    budget_ms=hook_budget(BUDGET_KEYS[kind]), json_output=fmt != "text",
                    watchdog=True, start=start)


def hook_main(argv: list[str], start: float | None = None) -> int:
    """``iaso hook <event> --host X --format F``: a host's hook entry point."""
    start = time.monotonic() if start is None else start
    opts, rest = _options(argv, ("--notify", "--unseen"), ("--host", "--format", "--root"))
    if not rest or rest[0] in ("-h", "--help"):
        sys.stdout.write(_HOOK_USAGE)
        return 0 if rest else 2
    kind = EVENTS.get(rest[0])
    host = str(opts.get("--host") or "claude-code")
    fmt = str(opts.get("--format") or "claude")
    if kind is None or fmt not in FORMATS:
        sys.stderr.write(f"iaso: unknown hook event or format\n{_HOOK_USAGE}")
        return 2
    data: dict[str, Any] = {}
    if opts.get("--notify"):  # Codex's notify passes the turn's JSON as the last argument
        for arg in reversed(rest[1:]):
            try:
                parsed = json.loads(arg)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                data = parsed
                break
        data = {**data, "stop_hook_active": True, "stop_active": True}
    else:
        from iaso.hosts.claude_code.hookio import read_input, use_utf8_stdio

        use_utf8_stdio()
        data = read_input(sys.stdin)
    display = ("status" if opts.get("--notify") else
               "unseen" if opts.get("--unseen") else "owner")
    return run_event(kind, data, host=host, fmt=fmt, root=opts.get("--root"), start=start,
                     display=display)


# --------------------------------------------------------------------------- turn


def _session(opts: dict[str, Any]) -> str:
    return str(opts.get("--session") or os.environ.get("IASO_SESSION_ID") or "cli")


def _turn_root(opts: dict[str, Any]) -> Path | None:
    from iaso.hosts.claude_code.hookio import find_hook_root

    return find_hook_root({"cwd": os.getcwd()}, opts.get("--root"))


def turn_main(argv: list[str]) -> int:
    opts, rest = _options(argv, (), ("--session", "--prompt-file", "--format", "--root"))
    if not rest or rest[0] in ("-h", "--help") or rest[0] not in ("start", "end"):
        sys.stdout.write(_TURN_USAGE)
        return 0 if rest and rest[0] in ("-h", "--help") else 2
    fmt = str(opts.get("--format") or "text")
    if fmt not in ("text", "json"):
        sys.stderr.write(_TURN_USAGE)
        return 2
    root = _turn_root(opts)
    if root is None:
        return 0  # repository not adopted by iaso: nothing to do
    from iaso.hosts.claude_code.hookio import read_json, safe_session_id, use_utf8_stdio

    use_utf8_stdio()
    session = safe_session_id(_session(opts))
    base = {"session_id": session, "cwd": str(root)}
    state_dir = root / ".iaso" / "session" / session
    if rest[0] == "start":
        path = opts.get("--prompt-file")
        try:
            text = (Path(path).read_text(encoding="utf-8") if path
                    else ("" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()))
        except OSError as exc:
            sys.stderr.write(f"iaso: cannot read the prompt: {exc}\n")
            text = ""
        first = not (state_dir / "turn.json").exists()  # the session's first turn
        if first:  # a new conversation: forget what earlier hooks injected (as the brief)
            try:
                from iaso.present.delta import reset

                reset(root / ".iaso" / "session", session)
            except Exception:  # noqa: BLE001 - never block the turn on session state
                pass
        # The owner's message first: it is logged and the turn started (turn.json) before
        # anything slower runs, so the brief reaching the watchdog (which ends the process)
        # can never drop the prompt; a relay or capture needs its digest (R13 Q4).
        run_event("prompt", {**base, "prompt": text}, host="cli", fmt=fmt, root=str(root))
        if first:  # then the session brief, under its own budget and watchdog; "resume"
            # keeps what the prompt event just injected
            run_event("session-start", {**base, "source": "resume"}, host="cli", fmt=fmt,
                      root=str(root))
        return 0
    # turn end: at most one block per turn, never on a second `turn end` of the same turn
    turn = read_json(state_dir / "turn.json")
    digest = turn.get("prompt_digest") if isinstance(turn, dict) else None
    ended = read_json(state_dir / "turn-end.json")
    active = bool(digest) and isinstance(ended, dict) and ended.get("prompt_digest") == digest
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "turn-end.json").write_text(json.dumps({"prompt_digest": digest}),
                                                 encoding="utf-8")
    except OSError:
        pass
    return run_event("stop", {**base, "stop_hook_active": active}, host="cli", fmt=fmt,
                     root=str(root))


# --------------------------------------------------------------------------- hosts


def hosts_main(argv: list[str]) -> int:
    import argparse
    import importlib

    from iaso.hosts.common import InstallError

    parser = argparse.ArgumentParser(prog="iaso hosts", description=(
        "Thin adapters for Codex and Hermes over the host-neutral turn API, each with "
        "the CLI-only fallback (iaso turn start/end)."))
    parser.add_argument("action", choices=("install", "uninstall", "status"))
    parser.add_argument("host", nargs="?", choices=tuple(ADAPTERS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--launcher", default="auto", choices=("auto", "path", "venv", "uv"))
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    from iaso.hosts.claude_code.hookio import find_hook_root

    root = find_hook_root({"cwd": os.getcwd()}, args.root)
    if root is None:
        print("iaso: no .iaso/ here; run iaso init first", file=sys.stderr)
        return 2
    if args.action != "status" and args.host is None:
        parser.error(f"{args.action} needs a host: codex or hermes")
    hosts = [args.host] if args.host else list(ADAPTERS)
    try:
        for host in hosts:
            module = importlib.import_module(ADAPTERS[host])
            if args.action == "status":
                for line in module.status(root):
                    print(f"{host}: {line}")
                continue
            if args.action == "install":
                report = module.install(root, launcher=args.launcher, dry_run=args.dry_run)
            else:
                report = module.uninstall(root, dry_run=args.dry_run)
            verb = "would change" if args.dry_run else "changed"
            print(f"iaso hosts {args.action} {host}: {verb} "
                  + (", ".join(report.changed) or "nothing"))
            for line in report.lines:
                print(f"  {line}")
    except InstallError as exc:
        print(f"iaso: {exc}", file=sys.stderr)
        return 1
    return 0


def run(command: str, argv: list[str]) -> int:
    if command == "turn":
        return turn_main(argv)
    if command == "hook":
        return hook_main(argv)
    return hosts_main(argv)
