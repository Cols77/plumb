"""Routes ``plumb hook``, ``plumb hooks``, ``plumb install`` and ``plumb statusline``.

Hooks and the status line run every turn, so this module imports nothing at load time
beyond the standard library: each route imports only the module it needs, and
``argparse`` is loaded only for the installer commands.
"""

from __future__ import annotations

import sys
import time

HOOK_MODULES: dict[str, str] = {
    "session-start": "plumb.hosts.claude_code.session_start",
    "prompt": "plumb.hosts.claude_code.prompt",
    "post-edit": "plumb.hosts.claude_code.post_edit",
    "edit-check": "plumb.hosts.claude_code.edit_check",
    "question-answer": "plumb.hosts.claude_code.question_answer",
    "stop": "plumb.hosts.claude_code.stop",
    "subagent-stop": "plumb.hosts.claude_code.subagent_stop",
    "session-end": "plumb.hosts.claude_code.session_end",
    "pre-tool": "plumb.hosts.claude_code.pretool",  # SHOW's module; until then it allows
}

_HOOK_USAGE = ("usage: plumb hook {session-start|prompt|post-edit|edit-check|question-answer|stop|subagent-stop|session-end|pre-tool} [--root PATH]\n"
               "Claude Code hook entry points: read the host's JSON on stdin, answer on "
               "stdout, always exit 0.\n")


def _root_option(argv: list[str]) -> tuple[str | None, list[str]]:
    root = None
    rest: list[str] = []
    it = iter(argv)
    for arg in it:
        if arg == "--root":
            root = next(it, None)
        elif arg.startswith("--root="):
            root = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    return root, rest


def _cannot_run(root: str | None, event: str, why: str) -> None:
    """One line naming the check and why it did not run, appended to the adopted project's
    ``.plumb/session/errors.log`` (SR-354 EX-2); a project not adopted gets nothing (EX-3)."""
    try:
        from plumb.hosts.claude_code.hookio import find_hook_root

        adopted = find_hook_root({}, root)
        if adopted is None:
            return
        path = adopted / ".plumb" / "session" / "errors.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = " ".join(f"{stamp} plumb hook {event}: {why}".split())
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except Exception:  # noqa: BLE001 - the copy itself may be half gone; never block the turn
        pass


def _hook(argv: list[str]) -> int:
    start = time.monotonic()
    if any(a.split("=", 1)[0] in ("--host", "--format") for a in argv):
        from plumb.hosts.cli import hook_main  # sp4 3.1: any host through hosts.neutral

        return hook_main(argv, start)
    root, rest = _root_option(argv)
    if not rest or rest[0] in ("-h", "--help"):
        sys.stdout.write(_HOOK_USAGE)
        return 0 if rest else 2
    event = rest[0]
    module_name = HOOK_MODULES.get(event)
    if module_name is None:
        sys.stderr.write(f"plumb: unknown hook '{event}'\n" + _HOOK_USAGE)
        return 2
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        if event == "pre-tool":
            return 0  # stub: allow (no output)
        # a hook missing from this build, or a copy changed under a running session (a
        # reinstall), never blocks the turn, but is not silent either: one line in an
        # adopted project's errors.log, nothing in a project not adopted (SR-354 EX-2, EX-3)
        sys.stderr.write(f"plumb: hook '{event}' is not available in this build\n")
        _cannot_run(root, event, f"its code could not be loaded ({exc})")
        return 0
    return int(module.main(root=root, watchdog=True, start=start) or 0)


def _statusline(argv: list[str]) -> int:
    root, rest = _root_option(argv)
    if rest and rest[0] in ("-h", "--help"):
        sys.stdout.write("usage: plumb statusline [--root PATH]\nPrints the one-line plumb "
                         "status from .plumb/session/status.json; recomputes nothing.\n")
        return 0
    from plumb.hosts.claude_code import statusline

    return statusline.main(root=root)


def run(command: str, argv: list[str]) -> int:
    if command == "hook":
        return _hook(argv)
    if command == "statusline":
        return _statusline(argv)
    from plumb.hosts.claude_code import install

    return install.run_cli(command, argv)
