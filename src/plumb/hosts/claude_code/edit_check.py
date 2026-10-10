"""PostToolUse on Edit, Write, MultiEdit and NotebookEdit: the stale-link notice (SR-111).

The synchronous companion of ``post-edit`` (which stays asynchronous and only tracks the
edit): right after an edit it names, one line each and at most five, the links the edit made
stale, from the link map (``.plumb/cache/linkmap.json``) and the hash cache, and, when a
record file was edited directly, the records that derive from it. It prints them as
``additionalContext`` so the agent reads them in the same turn. A missing map says nothing
(the stop hook is the backstop); a map older than the records is rebuilt first, inside the
hook's deadline. Each link state is said once per session.
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from plumb.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, run_hook
from plumb.hosts.claude_code.post_edit import repo_relative


def _edited_path(ctx: HookContext) -> str | None:
    tool_input = ctx.data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str):
        return None
    cwd = ctx.data.get("cwd")
    return repo_relative(ctx.root, raw, cwd if isinstance(cwd, str) else None)


def handle(ctx: HookContext) -> HookOutput | None:
    rel = _edited_path(ctx)
    if rel is None or rel.startswith(".plumb/session/") or rel.startswith(".plumb/cache/"):
        return None
    from plumb import stale

    root = ctx.root
    if stale.load_linkmap(root) is None:
        return None  # no map yet: the stop hook says it
    core = None
    if stale.linkmap_outdated(root) and not ctx.deadline.expired():
        from plumb.api import open_core

        core = open_core(root)
        stale.ensure_linkmap(core)
    baseline = stale.read_baseline(root, ctx.session_id)
    said: list[tuple[str, str, str]] = []  # (told key, state, line)
    for item in stale.stale_after_edit(root, rel):
        before = baseline.get(item.link)
        if isinstance(before, dict) and (before.get("now") or [None, None])[1] == item.now:
            continue  # stale before the turn and not moved by it
        state = item.now or "missing"
        if stale.was_told(root, ctx.session_id, item.link, state):
            continue
        said.append((item.link, state, stale.notice(item)))
    record = stale.record_for_path(root, rel)
    if record is not None and not ctx.deadline.expired():
        if core is None:
            from plumb.api import open_core

            core = open_core(root)
        index = core.index()
        for source, target, link, kind in stale.derived_stale(core, [record]):
            state = f"{link}|{index[target].hash}"
            before = baseline.get(link)
            if isinstance(before, dict) and (before.get("now") or [None, None])[1] == (
                    index[target].hash):
                continue
            if stale.was_told(root, ctx.session_id, f"derived:{link}", state):
                continue
            said.append((f"derived:{link}", state, stale.derived_line(source, target, kind)))
    if not said:
        return None
    shown = said[:stale.MAX_NOTICES]
    lines = [line for _key, _state, line in shown]
    if len(said) > len(shown):
        lines.append(f"plumb: +{len(said) - len(shown)} more")
    stale.mark_told(root, ctx.session_id, {key: state for key, state, _line in shown})
    return HookOutput(additional_context="\n".join(lines))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("edit-check", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("post_edit"), json_output=True, watchdog=watchdog,
                    start=start)
