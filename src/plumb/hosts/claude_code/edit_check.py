"""PostToolUse on Edit, Write, MultiEdit and NotebookEdit: the stale-link notice (SR-111) and
the requirements the file serves (SR-374 EX-3, from ``plumb.present.insights``).

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

from plumb.hosts.claude_code.hookio import (
    HookContext,
    HookOutput,
    _plumb_root,
    hook_budget,
    read_json,
    run_hook,
    write_json_atomic,
)
from plumb.hosts.claude_code.post_edit import repo_relative


def _edited_path(ctx: HookContext) -> tuple[Path, str] | None:
    """``(root, path in it)``: the file's own adopted root when it lies outside this one (a
    workflow agent in another worktree), recorded for the subagent-stop hook (SR-166)."""
    tool_input = ctx.data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str):
        return None
    cwd = ctx.data.get("cwd")
    cwd = cwd if isinstance(cwd, str) else None
    root = ctx.root
    rel = repo_relative(root, raw, cwd)
    if rel is None and Path(raw).is_absolute():
        other = _plumb_root(Path(raw).parent)
        rel = repo_relative(other, raw, cwd) if other is not None else None
        root = other if rel is not None and other is not None else root
    if rel is None:
        return None
    return root, rel


def _note_stale(ctx: HookContext, root: Path, link_ids: list[str]) -> None:
    """Record, per agent and root, the stale links this edit's notices named, so the
    subagent-stop hook re-checks only those (``agent_roots.json``, SR-166)."""
    path = ctx.session_dir / "agent_roots.json"
    roots = read_json(path)
    roots = roots if isinstance(roots, dict) else {}
    agent = str(ctx.data.get("agent_id") or "main")
    mine = roots.get(agent) if isinstance(roots.get(agent), dict) else {}
    known = mine.get(str(root)) or []
    if str(root) in mine and set(link_ids) <= set(known):
        return
    mine[str(root)] = [*dict.fromkeys([*known, *link_ids])]
    roots[agent] = mine
    write_json_atomic(path, roots)


def handle(ctx: HookContext) -> HookOutput | None:
    edited = _edited_path(ctx)
    if edited is None:
        return None
    root, rel = edited
    if rel.startswith(".plumb/session/") or rel.startswith(".plumb/cache/"):
        return None
    from plumb import stale

    core = None
    if stale.load_linkmap(root) is None:
        if root == ctx.root or ctx.deadline.expired():
            return None  # no map yet: the session's own stop hook says it
        from plumb.api import open_core  # a worktree no session prompted in: SR-166 EX-1

        core = open_core(root)
        stale.ensure_linkmap(core)
    elif stale.linkmap_outdated(root) and not ctx.deadline.expired():
        from plumb.api import open_core

        core = open_core(root)
        stale.ensure_linkmap(core)
    baseline = stale.read_baseline(root, ctx.session_id)
    said: list[tuple[str, str, str]] = []  # (told key, state, line)
    made: list[str] = []  # the stale links this edit made, told or not
    for item in stale.stale_after_edit(root, rel):
        before = baseline.get(item.link)
        if isinstance(before, dict) and (before.get("now") or [None, None])[1] == item.now:
            continue  # stale before the turn and not moved by it
        made.append(item.link)
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
            made.append(link)
            if stale.was_told(root, ctx.session_id, f"derived:{link}", state):
                continue
            said.append((f"derived:{link}", state, stale.derived_line(source, target, kind)))
    _note_stale(ctx, root, made)
    serves = _serves(ctx, root, rel, core)
    if not said and not serves:
        return None
    shown = said[:stale.MAX_NOTICES]
    lines = [*serves, *(line for _key, _state, line in shown)]
    if len(said) > len(shown):
        lines.append(f"plumb: +{len(said) - len(shown)} more")
    stale.mark_told(root, ctx.session_id, {key: state for key, state, _line in shown})
    return HookOutput(additional_context="\n".join(lines))


def _serves(ctx: HookContext, root: Path, rel: str, core: object) -> list[str]:
    """SR-374 EX-3: the requirements the edited file serves, their examples and covering
    tests, from the insight table, once per session per record state."""
    from plumb import stale

    if root != ctx.root or not stale.links_touching(root, rel) or ctx.deadline.expired():
        return []
    from plumb.present import insights
    from plumb.present.delta import open_emitter

    if core is None:
        from plumb.api import open_core

        core = open_core(root)
    emitter = open_emitter(ctx, "edit", config=core.config)  # type: ignore[attr-defined]
    out = emitter.add(insights.lines("edit", core, {"path": rel}))
    emitter.close()
    return out


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False,
         start: float | None = None) -> int:
    return run_hook("edit-check", handle, stdin=stdin, stdout=stdout, root=root,
                    budget_ms=hook_budget("post_edit"), json_output=True, watchdog=watchdog,
                    start=start)
