"""Thin router of ``plumb understand``, ``settle``, ``undo``, ``go`` and ``clarify``."""

from __future__ import annotations

import importlib
import sys

ROUTES: dict[str, str] = {
    "understand": "plumb.understand.cmd_worker",
    "settle": "plumb.understand.cmd_settle",
    "undo": "plumb.understand.cmd_settle",
    "go": "plumb.understand.cmd_go",
}


def run(command: str, argv: list[str]) -> int:
    if command == "clarify":
        # `--wait` collects the check of the request; without it, today's helper
        from plumb.understand import cmd_clarify

        return int(cmd_clarify.run(command, argv) or 0)
    if command == "understand" and argv and argv[0] == "eval":
        from plumb.understand import evalrun

        return evalrun.run("eval", argv[1:])
    if command == "understand" and argv and argv[0] == "backlog":
        from plumb.understand import backlog

        return int(backlog.run("backlog", argv[1:]) or 0)
    module_name = ROUTES.get(command)
    if module_name is None:
        print(f"plumb: unknown command '{command}'", file=sys.stderr)
        return 2
    return int(importlib.import_module(module_name).run(command, argv) or 0)
