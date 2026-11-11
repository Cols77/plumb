"""SubagentStop: a workflow agent does not finish with a stale link of its own work (SR-166).

``edit-check`` records, per agent and root, the stale links its notices named for that agent's
edits (``agent_roots.json``); links already stale before the turn are not recorded. Only those
links are re-checked here, so the hook fits the stop budget: the ones still stale and held by
no card block the stop once, named as the main session's hold names them (an agent that
edited nothing is never held); a second stop (``stop_hook_active``) lets it go with a stale
card per link. Never fails the stop.
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from iaso.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, read_json, run_hook


def _recorded(ctx: HookContext) -> dict[Path, list[str]]:
    """The roots this agent edited in and the stale link ids edit-check named there."""
    recorded = read_json(ctx.session_dir / "agent_roots.json")
    recorded = recorded if isinstance(recorded, dict) else {}
    mine = recorded.get(str(ctx.data.get("agent_id") or "main"))
    if not isinstance(mine, dict):
        return {}    # it edited nothing
    return {Path(root): [str(i) for i in ids] for root, ids in mine.items()
            if isinstance(ids, list) and ids}


def handle(ctx: HookContext) -> HookOutput | None:
    try:
        recorded = _recorded(ctx)
        if not recorded:
            return None  # imports below cost the budget: an agent that edited nothing skips them
        from iaso import stale

        active = bool(ctx.data.get("stop_hook_active"))
        reasons: list[str] = []
        for root, ids in recorded.items():
            from iaso.api import open_core
            from iaso.hosts.claude_code.stop import question_released

            core = open_core(root)
            wanted = set(ids) - stale.asked_links(core, ctx.session_id)
            if not wanted:
                continue
            rows = stale.stale_rows(core, {i.split("#")[0] for i in wanted}, wanted)
            if not rows:
                continue
            if active:
                question_released(core, ctx.session_id, rows, core.index(), 1)
            else:
                reasons += [*stale.hold_lines(rows, 1, 1)]
        return HookOutput(block_reason="\n".join(reasons)) if reasons else None
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return None


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("subagent-stop", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("stop"), json_output=True, watchdog=watchdog,
                    start=start)
