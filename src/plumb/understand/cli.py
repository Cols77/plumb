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
        # today's function, unchanged, until SHOW's cmd_clarify replaces it
        from plumb.capture import cli as capture_cli

        return int(capture_cli.run(command, argv) or 0)
    if command == "understand" and argv and argv[0] == "eval":
        from plumb.understand import evalrun

        return evalrun.run("eval", argv[1:])
    module_name = ROUTES.get(command)
    if module_name is None:
        print(f"plumb: unknown command '{command}'", file=sys.stderr)
        return 2
    return int(importlib.import_module(module_name).run(command, argv) or 0)
