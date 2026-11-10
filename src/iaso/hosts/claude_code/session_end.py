"""SessionEnd: mark the session's folder as ended (``ended.json`` with the time), so the next
landing removes it (owner, 2026-10-20: "End-of-session hook"). Writes one small file, prints
nothing, never fails the host."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TextIO

from iaso.hosts.claude_code.hookio import HookContext, HookOutput, run_hook, write_json_atomic

MARKER = "ended.json"


def handle(ctx: HookContext) -> HookOutput | None:
    folder = ctx.session_dir / ctx.session_id
    if folder.is_dir():  # a session that left no folder has nothing to tidy
        write_json_atomic(folder / MARKER, {"ended": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                  time.gmtime()),
                                            "reason": str(ctx.data.get("reason") or "")})
    return None


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("session-end", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=5000, watchdog=watchdog, start=start)
