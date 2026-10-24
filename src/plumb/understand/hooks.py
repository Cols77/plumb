"""What the prompt hook asks of the understanding layer (plan 3.2 item 6)."""

from __future__ import annotations

from typing import Any


def on_prompt(ctx: Any, core: Any, entry: Any) -> list[str]:
    """After the prompt is logged: ``read.on_prompt`` (returns the id of the read job it
    queued, or None), then ``clarify.on_prompt(after=<that id>)`` (its job ``needs`` the read
    job), then ``queue.retry_failed``. Returns agent-facing lines. Never raises: a failing
    understand layer never blocks the prompt."""
    lines: list[str] = []
    try:
        from plumb import study

        if core is not None:    # SR-360 EX-2: a study whose records changed is marked
            study.out_of_date(ctx.root, core.index())
        # SR-294 EX-8: the ideas the owner accepted in the band, to write at their depth
        lines.extend(study.accepted_lines(ctx.root))
    except Exception:  # noqa: BLE001 - the prompt is never blocked
        pass
    try:
        from plumb.understand import clarify, queue, read, typed

        lines.extend(typed.on_prompt(core, entry, getattr(ctx, "session_id", "")))
        read_job = read.on_prompt(ctx, core, entry)
        lines.extend(clarify.on_prompt(ctx, core, entry, after=read_job))
        queue.retry_failed(core, getattr(ctx, "session_id", ""))
    except Exception:  # noqa: BLE001 - the prompt is never blocked
        return lines
    return lines
