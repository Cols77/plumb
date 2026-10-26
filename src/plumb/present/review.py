"""``plumb review`` (``/plumb review``): the deep review, in the owner's terms (sp5 6.2).

1. what awaits the owner: the records waiting on a judge, escalated sets awaiting approval,
   decisions that matter;
2. approvals the owner did not type (agent-relayed, judge-approved) since the last merge evidence,
   for a glance, each judge approval with its label;
3. drift: stale and dangling links, unconfirmed edits, failing acceptance tests, and CAPTURE's
   hidden-dependency and ownership hints;
4. alignment: ``plumb align`` for the scope, weakest edges first, with the gaps;
5. the merge state against ``merge.default_base`` in one line (``plumb.boundary``).

Every part degrades to one line when its lane is missing. Nothing here approves anything.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any

EDGES_SHOWN = 5


def _in_scope(record_id: str, scope: set[str] | None) -> bool:
    return scope is None or record_id in scope


def _awaiting(core: Any, scope: set[str] | None) -> list[str]:
    lines = ["1. awaits you:"]
    index = core.index()
    statuses = core.status()
    pending = [i for i, s in sorted(statuses.items()) if s.confirmation != "confirmed"
               and _in_scope(i, scope)]
    if pending:
        from plumb.present.owner_text import AWAITS_JUDGE

        n = len(pending)
        lines.append("  " + AWAITS_JUDGE.format(n=n, s="" if n == 1 else "s"))
    try:
        from plumb.capture import spec

        anchors = sorted(set(spec.set_of(core).values()))
        for anchor in anchors:
            if _in_scope(anchor, scope) and spec.set_state(core, anchor) != "approved":
                lines.append(f"  the set \"{index[anchor].title}\" waits on a judge, "
                             "as a whole")
    except Exception:  # noqa: BLE001 - an absent lane: no escalated sets to list
        pass
    for record_id, record in sorted(index.items()):
        if record.kind == "decision" and record.fields.get("matters") is True \
                and statuses[record_id].confirmation != "confirmed" \
                and _in_scope(record_id, scope):
            lines.append(f"  question \"{record.title}\": assumed "
                         f"{record.fields.get('chosen') or '?'}")
    if len(lines) == 1:
        lines.append("  nothing")
    return lines


def _glance(core: Any, scope: set[str] | None) -> list[str]:
    from types import SimpleNamespace

    from plumb.confirm import judge_auto
    from plumb.present.cards import judge_label

    lines = ["2. approvals you did not type (a glance; to undo one, say so in conversation, "
             "naming it by its title):"]
    entries = list(core.log_read("events"))
    start = 0
    for n, entry in enumerate(entries):
        if entry.kind == "merge-evidence":
            start = n + 1
    index = core.index()
    for entry in entries[start:]:
        by = entry.payload.get("by")
        if entry.kind != "approval" or by not in ("agent-relayed", "auto-jev", "auto-model"):
            continue
        for item in entry.payload.get("records") or []:
            record_id = str(item.get("id"))
            if not _in_scope(record_id, scope) or record_id not in index:
                continue
            if by in ("auto-jev", "auto-model"):     # SR-251
                how = str(judge_label(SimpleNamespace(approved_by=by,
                                                      auto=judge_auto(entry.payload))))
            else:
                how = f"relayed from your words \"{entry.payload.get('quote') or ''}\""
                if entry.payload.get("prompt_objects") is True:
                    how += " (the same message also objected or asked for a change)"
            lines.append(f"  \"{index[record_id].title}\" {how}, {entry.at}")
    if len(lines) == 1:
        lines.append("  none")
    return lines


def _changed(core: Any, base: str) -> list[str]:
    """Paths changed since the merge base, committed or not (untracked files too), as
    ``plumb merge-check`` reads them; without the base, the working tree's own changes."""
    try:
        from plumb.merge import changed_paths

        return list(changed_paths(core, base)[0])
    except Exception:  # noqa: BLE001 - no such base, or no MERGE lane: the tree's changes
        pass
    paths: list[str] = []
    for args in (["diff", "--name-only", "HEAD"],
                 ["ls-files", "--others", "--exclude-standard"]):
        try:
            out = subprocess.run(["git", *args], cwd=core.root, capture_output=True,
                                 text=True, timeout=5, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0:
            paths += [p.strip() for p in out.stdout.splitlines() if p.strip()]
    return sorted(set(paths))


def _drift(core: Any, scope: set[str] | None, base: str) -> list[str]:
    from plumb.commands import drift_data

    data = drift_data(core)
    lines = ["3. drift:"]

    def keep(link_id: str) -> bool:
        return _in_scope(link_id.split("#", 1)[0], scope)

    stale = [s for s in data["stale"] if keep(s["link"])]
    dangling = [d for d in data["dangling"] if keep(d["link"])]
    if stale:
        shown = "; ".join(f"{s['link']} -> {s['target']} ({s['moved']} moved)"
                          for s in stale[:3])
        lines.append(f"  {len(stale)} stale link(s): {shown}"
                     + (f" +{len(stale) - 3} more" if len(stale) > 3 else ""))
    if dangling:
        lines.append(f"  {len(dangling)} dangling link(s): "
                     + "; ".join(f"{d['link']} -> {d['target']}" for d in dangling[:3]))
    for record_id in data["unconfirmed_edits"]:
        if _in_scope(record_id, scope):
            lines.append(f"  {record_id} changed since you confirmed it")
    for record_id in data["failing"]:
        if _in_scope(record_id, scope):
            lines.append(f"  {record_id} has a failing acceptance test")
    changed = _changed(core, base)
    try:
        from plumb.capture import api

        for hint in api.drift_hints(core, changed):
            lines.append("  hint: " + str(hint).removeprefix("plumb: ").removeprefix("hint: "))
        from plumb.trace import untraced_paths

        untraced = list(untraced_paths(core, changed))
        for path, proposal in api.ownership_proposals(core, untraced).items():
            line = getattr(proposal, "line", "") or f"{path}: proposed owner " \
                f"{getattr(proposal, 'proposed', None) or 'none'}"
            lines.append("  ownership: " + str(line).removeprefix("plumb: "))
    except Exception:  # noqa: BLE001 - CAPTURE absent: no hints
        pass
    if len(lines) == 1:
        lines.append("  none")
    return lines


def _alignment(core: Any, ids: Sequence[str] | None) -> list[str]:
    try:
        from plumb.align import align, align_lines
    except ImportError:
        return ["4. alignment: unavailable"]
    try:
        result = align(core, list(ids) if ids else None)
    except Exception as exc:  # noqa: BLE001
        return [f"4. alignment: unavailable ({exc})"]
    return ["4. alignment:"] + ["  " + line for line in align_lines(result,
                                                                     limit=EDGES_SHOWN)]


def _merge(core: Any, base: str) -> list[str]:
    try:
        from plumb.boundary import merge_report
    except ImportError:
        return ["5. merge state: unavailable"]
    try:
        report = merge_report(core, base, run_full=False)
    except Exception as exc:  # noqa: BLE001
        return [f"5. merge state: unavailable ({exc})"]
    code = int(getattr(report, "exit", 0) or 0)
    meaning = {0: "ready", 1: "findings to fix", 4: "waits on a judge or your answer",
               5: "verification holds it"}.get(code, f"exit {code}")
    awaiting = len(getattr(report, "awaiting", ()) or ())
    untraced = len(getattr(report, "untraced", ()) or ())
    lines = [f"5. merge state against {base}: {meaning} ({awaiting} awaiting you, "
             f"{untraced} untraced; plumb merge-check {base})"]
    conflicts = getattr(report, "intent_conflicts", ()) or ()
    if conflicts:  # sp6 8.3: each intent conflict a merge left, as its card
        from plumb.present.owner_text import CONFLICTS_HEADER

        lines.append("  " + CONFLICTS_HEADER)
        for conflict in conflicts:
            lines.extend("  " + str(line) for line in conflict.get("card") or [])
    return lines


def review(core: Any, ids: Sequence[str] | None = None) -> dict[str, Any]:
    """The five sections, scoped to ``ids`` (resolved from the owner's words) when given."""
    merge = getattr(core.config, "merge", None)
    base = str(getattr(merge, "default_base", "main") or "main")
    scope = set(ids) if ids else None
    if scope:
        index = core.index()
        for record_id in list(scope):
            record = index.get(record_id)
            for link in getattr(record, "links", ()):
                if link.target.record:
                    scope.add(link.target.record)
    sections = [_awaiting(core, scope), _glance(core, scope), _drift(core, scope, base),
                _alignment(core, ids), _merge(core, base)]
    header = "plumb review" + (f" of {', '.join(ids)}" if ids else "") + \
        " (it approves nothing)"
    lines = [header] + [line for section in sections for line in section]
    return {"lines": lines, "scope": sorted(scope) if scope else None}
