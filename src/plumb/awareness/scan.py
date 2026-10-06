"""Reading what the other worktrees and branches are changing, read-only (sp6 9.3, SR-078,
SR-079).

``overlaps(core, mine)`` lists, for each record of ``mine``, the other places changing it:

- every other worktree, found from git's files (no git process): its
  ``.plumb/cache/changing.json``, ignored when older than ``awareness.max_age_days``; its
  paths are mapped with this reader's own index too, so a stale ``records`` map does not hide
  a changed end;
- branches without a worktree, from ``.plumb/cache/awareness-branches.json``; with
  ``scan_branches`` (the session start only) the branches whose tip moved are rescanned first,
  newest first, one ``git diff`` each, at most ``awareness.branch_max`` and
  ``awareness.branch_scan_ms``; an unmoved tip runs no git;
- intent in flight other branches claimed in ``refs/plumb/claims`` (R17), read from git's
  files and this worktree's cache.

Nothing is written outside this worktree's ``.plumb/cache/``; no lock is taken anywhere; no
git command runs in another worktree's directory. A ``deadline`` (``expired()``) that runs out
stops the read: what was found is returned and "plumb: awareness skipped (budget)" goes to
the error log, never to the owner.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from plumb.awareness import gitfiles
from plumb.awareness.publish import CHANGING, default_branch, read_changing
from plumb.contracts import Overlap

BRANCH_CACHE = "awareness-branches.json"
SKIPPED = "plumb: awareness skipped (budget)"
GIT_TIMEOUT_S = 1.0
_RECORD_DIRS = {"intents": "INT", "requirements": "SR", "decisions": "DEC",
                "features": "FEAT", "ncs": "NC"}


def _expired(deadline: Any) -> bool:
    try:
        return bool(deadline is not None and deadline.expired())
    except Exception:  # noqa: BLE001 - a deadline that cannot answer never stops the read
        return False


def skipped(root: Path, where: str) -> None:
    """The budget ran out: one line in the error log, nothing for the owner."""
    try:
        from plumb.hosts.claude_code.hookio import log_error

        log_error(Path(root), "awareness", f"{SKIPPED}: {where}")
    except Exception:  # noqa: BLE001 - logging never fails a hook
        pass


def _config(core: Any) -> Any:
    from plumb.config import AwarenessConfig

    return getattr(core.config, "awareness", None) or AwarenessConfig()


def _raw_hash(path: Path) -> str | None:
    try:
        return "raw:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _from_worktree(core: Any, wt: gitfiles.Worktree, mine: set[str], max_age_s: float,
                   now: float) -> list[Overlap]:
    path = wt.path / ".plumb" / "cache" / CHANGING
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if now - mtime > max_age_s:
        return []  # a worktree nobody has worked in for a week is not "changing" anything
    data = read_changing(path)
    if data is None:
        return []
    raw_records = data.get("records")
    records: Mapping[str, Any] = raw_records if isinstance(raw_records, Mapping) else {}
    found: dict[str, dict[str, str]] = {}
    for record_id, item in records.items():
        if record_id in mine and isinstance(item, Mapping):
            found[record_id] = {k: str(item.get(k) or "") for k in ("title", "hash", "how")}
    paths = [str(p) for p in data.get("paths") or [] if isinstance(p, str)]
    index = core.index()
    if paths and not mine <= set(found):
        for rel, ids in core.records_for_paths(paths).items():
            for record_id in ids:
                if record_id in mine and record_id not in found and record_id in index:
                    record = index[record_id]
                    how = "edited" if record.path == rel else "ends"
                    found[record_id] = {"title": record.title, "hash": "", "how": how}
    out: list[Overlap] = []
    branch = wt.branch or (f"detached {wt.head[:7]}" if wt.head else wt.path.name)
    for record_id, item in sorted(found.items()):
        other = item["hash"]
        record = index.get(record_id)
        if record is not None:  # the other side edited its file since it published
            file = wt.path / record.path
            try:
                newer = file.stat().st_mtime > mtime
            except OSError:
                newer = False
            if newer or not other:
                other = _raw_hash(file) or other or str(data.get("at") or "")
        out.append(Overlap(record=record_id, title=item["title"] or getattr(record, "title", ""),
                           branch=branch, worktree=wt.path.as_posix(), how=item["how"],
                           other_hash=other, at=str(data.get("at") or "")))
    return out


# ------------------------------------------------------------------ branches without a worktree


def branch_cache_path(root: Path) -> Path:
    return Path(root) / ".plumb" / "cache" / BRANCH_CACHE


def read_branch_cache(root: Path) -> dict[str, Any]:
    try:
        data = json.loads(branch_cache_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"branches": {}}
    if not isinstance(data, dict) or not isinstance(data.get("branches"), dict):
        return {"branches": {}}
    return data


def _write_branch_cache(root: Path, data: Mapping[str, Any]) -> None:
    path = branch_cache_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError:
        pass


def _diff(root: Path, default: str, tip: str) -> list[str] | None:
    try:
        result = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z",
                                 f"{default}...{tip}"], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return sorted(p for p in result.stdout.split("\0") if p)


def refresh_branches(core: Any, *, deadline: Any = None, skip: Iterable[str] = ()
                  ) -> dict[str, Any]:
    """Rescan the local branches whose tip moved (session start only), within
    ``awareness.branch_max`` and ``awareness.branch_scan_ms``; the rest keep their cached
    result for a later session start. Returns the cache."""
    root = Path(core.root)
    common = gitfiles.common_dir(root)
    cache = read_branch_cache(root)
    if common is None:
        return cache
    config = _config(core)
    default = default_branch(core)
    skipped_names = set(skip) | {default}
    tips = {b: t for b, t in gitfiles.branch_tips(common).items() if b not in skipped_names}
    branches: dict[str, Any] = {b: e for b, e in cache["branches"].items()
                                if b in tips and isinstance(e, dict)}
    moved = sorted((b for b in tips if branches.get(b, {}).get("tip") != tips[b]),
                   key=lambda b: (-gitfiles.ref_mtime(common, b), b))
    start = time.monotonic()
    cap_s = max(int(config.branch_scan_ms), 0) / 1000.0
    scanned = 0
    for branch in moved:
        if scanned >= int(config.branch_max):
            break
        if time.monotonic() - start >= cap_s or _expired(deadline):
            skipped(root, "branch scan")
            break
        paths = _diff(root, default, tips[branch])
        scanned += 1
        if paths is None:
            continue
        branches[branch] = {"tip": tips[branch], "paths": paths,
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    data = {"branches": branches, "default": default}
    if data != cache:
        _write_branch_cache(root, data)
    return data


def _record_of_file(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) == 3 and parts[0] == ".plumb" and parts[1] in _RECORD_DIRS \
            and parts[2].endswith(".md"):
        return parts[2][:-3]
    return None


def _from_branches(core: Any, cache: Mapping[str, Any], mine: set[str],
                   skip: set[str]) -> list[Overlap]:
    index = core.index()
    out: list[Overlap] = []
    for branch, entry in sorted((cache.get("branches") or {}).items()):
        if branch in skip or not isinstance(entry, Mapping):
            continue
        paths = [str(p) for p in entry.get("paths") or []]
        found: dict[str, str] = {}
        for rel in paths:
            own = _record_of_file(rel)
            if own in mine:
                found[own] = "edited"
        for rel, ids in core.records_for_paths(paths).items():
            for record_id in ids:
                if record_id in mine and record_id not in found:
                    record = index.get(record_id)
                    found[record_id] = ("edited" if record is not None and record.path == rel
                                        else "ends")
        for record_id, how in sorted(found.items()):
            record = index.get(record_id)
            out.append(Overlap(record=record_id, title=getattr(record, "title", ""),
                               branch=branch, how=how, other_hash=str(entry.get("tip") or ""),
                               at=str(entry.get("at") or "")))
    return out


# ------------------------------------------------------------------ the one entry point


def overlaps(core: Any, mine: Iterable[str], *, deadline: Any = None,
             scan_branches: bool = False) -> tuple[Overlap, ...]:
    """Every other place changing a record of ``mine`` (see the module docstring)."""
    config = _config(core)
    mine_set = {str(i) for i in mine}
    if not config.enabled or not mine_set:
        return ()
    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None:
        return ()
    out: list[Overlap] = []
    with_worktree: set[str] = set()
    now = time.time()
    max_age_s = float(config.max_age_days) * 86400.0
    for wt in gitfiles.worktrees(root):
        if wt.branch:
            with_worktree.add(wt.branch)
        if gitfiles.same_path(wt.path, root):
            continue
        if _expired(deadline):
            skipped(root, "worktrees")
            break
        out.extend(_from_worktree(core, wt, mine_set, max_age_s, now))
    skip = with_worktree | {me.branch or ""}
    if config.branches and not _expired(deadline):
        cache = (refresh_branches(core, deadline=deadline, skip=skip)
                 if scan_branches else read_branch_cache(root))
        out.extend(_from_branches(core, cache, mine_set, skip | {default_branch(core)}))
    if not _expired(deadline):
        try:
            from plumb.awareness import inflight

            out.extend(inflight.claim_overlaps(core, mine_set, me.branch))
        except Exception:  # noqa: BLE001 - intent in flight is advisory
            pass
    seen: set[tuple[str, str]] = set()
    unique: list[Overlap] = []
    for item in out:
        key = (item.record, item.branch)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(sorted(unique, key=lambda o: (o.record, o.branch)))
