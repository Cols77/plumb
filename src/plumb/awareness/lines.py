"""What the owner and the agent see of other worktrees' work (sp6 9.4, SR-078; R17).

- ``brief_lines``: the session brief's lines, one per overlap with this worktree's changing
  records, at most ``awareness.brief_lines`` then "+N more (/plumb status)", plus the
  intent conflicts other branches raised against this branch's work (build on the answer);
- ``delta_lines``: the prompt (and stop) hook's lines for the records it is about, keyed
  ``(overlap, record, branch, other side's hash)`` for ``present.delta``, so each shows once
  per session and again only when the other side's version changed;
- ``snapshot_fields``: ``overlaps`` and ``overlap_labels`` for the status card;
- ``status_section``: ``plumb status``'s list of everything other worktrees and branches are
  changing, with their worktree paths.

Wording comes from ``plumb.present.owner_text`` (sp6 11.1). Awareness informs: it never
blocks, never asks the owner, never stops an edit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.awareness import inflight
from plumb.awareness.publish import changing_path, read_changing
from plumb.awareness.scan import overlaps
from plumb.contracts import Overlap
from plumb.present import owner_text as text


def changing_ids(core: Any) -> set[str]:
    """The records this worktree is changing, from its own ``changing.json`` (its records,
    and its paths mapped with the current index)."""
    data = read_changing(changing_path(Path(core.root))) or {}
    ids = {str(i) for i in (data.get("records") or {})}
    paths = [str(p) for p in data.get("pending") or [] if isinstance(p, str)]
    if paths:
        for found in core.records_for_paths(paths).values():
            ids.update(found)
    index = core.index()
    return {i for i in ids if i in index}


def overlap_line(item: Overlap, *, worktree: bool = False) -> str:
    line = text.OVERLAP.format(id=item.record, title=item.title, branch=item.branch)
    if item.how == "claimed" and item.summary:
        line += text.OVERLAP_CLAIMED.format(summary=_clip(item.summary, 80))
    if worktree and item.worktree:
        line += text.OVERLAP_WORKTREE.format(worktree=item.worktree)
    return line


def _clip(value: str, width: int) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= width else value[: width - 3].rstrip() + "..."


def _config(core: Any) -> Any:
    from plumb.config import AwarenessConfig

    return getattr(core.config, "awareness", None) or AwarenessConfig()


def raised_lines(core: Any) -> list[tuple[str, str, str]]:
    """``(subject, state, line)`` for every intent conflict another branch raised against
    this branch's work (R17: both branches build on the one answer). No git process."""
    my_branch, claims = inflight.others(core)
    index = core.index()
    out: list[tuple[str, str, str]] = []
    for conflict in inflight.raised_for(core, my_branch, claims):
        record_id = str(conflict.get("record") or "")
        title = index[record_id].title if record_id in index else record_id
        branch = str(conflict.get("raised_on") or "")
        state = str(conflict.get("state") or "proposed")
        chosen = str(conflict.get("chosen") or "")
        if state == "confirmed" and chosen:
            line = text.EARLY_SETTLED.format(id=record_id, title=title, branch=branch,
                                             chosen=_clip(chosen, 120))
        else:
            line = text.EARLY_KNOWN.format(id=record_id, title=title, branch=branch)
        out.append((f"inflight:{branch}:{conflict.get('dec')}", f"{state}|{chosen}", line))
    return out


def brief_lines(core: Any, deadline: Any = None) -> list[str]:
    """The session brief's awareness lines (the branch scan runs here, within its cap)."""
    config = _config(core)
    if not config.enabled:
        return []
    found = overlaps(core, changing_ids(core), deadline=deadline, scan_branches=True)
    lines = [overlap_line(item) for item in found]
    cap = max(int(config.brief_lines), 0)
    if len(lines) > cap:
        lines = [*lines[:cap], text.MORE_OVERLAPS.format(n=len(lines) - cap)]
    try:
        lines += [line for _s, _st, line in raised_lines(core)]
    except Exception:  # noqa: BLE001 - intent in flight is advisory
        pass
    return lines


def delta_lines(core: Any, ids: Iterable[str]) -> list[Any]:
    """One ``present.delta.Line`` per overlap of ``ids`` and per conflict raised against
    this branch's work, keyed so a line repeats only when the other side changed."""
    from plumb.present.delta import Line

    if not _config(core).enabled:
        return []
    out = [Line(overlap_line(item), subject=f"overlap:{item.record}:{item.branch}",
                state=item.other_hash or item.at or "-", record=item.record)
           for item in overlaps(core, ids)]
    try:
        out += [Line(line, subject=subject, state=state)
                for subject, state, line in raised_lines(core)]
    except Exception:  # noqa: BLE001 - advisory
        pass
    return out


def snapshot_fields(core: Any, seen: Iterable[str] = ()) -> Mapping[str, Any]:
    """``overlaps`` and ``overlap_labels`` (the branches) for the status card; ``{}`` when
    nothing overlaps."""
    if not _config(core).enabled:
        return {}
    mine = changing_ids(core) | {str(i) for i in seen}
    found = overlaps(core, mine)
    if not found:
        return {}
    labels = tuple(sorted({item.branch for item in found}))
    return {"overlaps": len({item.record for item in found}), "overlap_labels": labels}


def card_text(snapshot: Mapping[str, Any], *, ascii: bool = False) -> list[str]:
    """The status card's overlap and conflict parts (sp6 8.3, 9.4); none when zero."""
    parts: list[str] = []
    try:
        n = int(snapshot.get("overlaps") or 0)
    except (TypeError, ValueError):
        n = 0
    if n:
        labels = ", ".join(str(b) for b in snapshot.get("overlap_labels") or ()) or "elsewhere"
        parts.append((text.OVERLAP_CARD_ASCII if ascii else text.OVERLAP_CARD)
                     .format(n=n, labels=labels))
    try:
        conflicts = int(snapshot.get("conflicts") or 0)
    except (TypeError, ValueError):
        conflicts = 0
    if conflicts:
        parts.append((text.CONFLICTS_CARD if conflicts == 1 else text.CONFLICTS_CARD_PLURAL)
                     .format(n=conflicts))
    return parts


def status_section(core: Any) -> list[str]:
    """``plumb status``: what every other worktree and branch is changing (the records this
    worktree also changes first), with worktree paths, and other branches' intent in
    flight."""
    index = core.index()
    mine = changing_ids(core)
    found = overlaps(core, list(index))
    if not found:
        lines = [text.STATUS_NO_OVERLAPS]
    else:
        ordered = sorted(found, key=lambda o: (o.record not in mine, o.record, o.branch))
        lines = [text.STATUS_OVERLAPS_HEADER,
                 *("  " + overlap_line(item, worktree=True) for item in ordered)]
    _me, claims = inflight.others(core, allow_git=True)
    if claims:
        lines.append(text.INFLIGHT_HEADER)
        for claim in claims:
            records = sorted((claim.get("records") or {}).items())
            names = ", ".join(f'{i} "{e.get("title", "")}"' for i, e in records[:4]
                              if isinstance(e, Mapping))
            if len(records) > 4:
                names += f", +{len(records) - 4} more"
            lines.append(text.INFLIGHT_LINE.format(branch=claim.get("branch"),
                                                   summary=_clip(str(claim.get("summary")
                                                                     or ""), 80),
                                                   records=names))
    return lines


def status_data(core: Any) -> dict[str, Any]:
    """``plumb status --json``'s overlap rows."""
    found = overlaps(core, list(core.index()))
    return {"overlaps": [dict(record=o.record, title=o.title, branch=o.branch,
                              worktree=o.worktree, how=o.how) for o in found]}


__all__: Sequence[str] = ("brief_lines", "card_text", "changing_ids", "delta_lines",
                          "overlap_line", "raised_lines", "snapshot_fields", "status_data",
                          "status_section")
