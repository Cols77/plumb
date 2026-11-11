"""Publishing what this worktree is changing, into its own cache only (sp6 9.1, 9.2, SR-079).

``.iaso/cache/changing.json`` (gitignored) holds the paths this worktree's branch changed
since its merge base with the default branch (``committed``, recomputed only when ``HEAD``
or the default branch's tip moved: one ``git merge-base`` and one ``git diff``; once the
default branch holds ``HEAD`` nothing committed is in flight), the paths changed since
(``pending``: the stop hook's turn paths and the post-edit hook's edits), and the records
those paths change. Other worktrees read it; nothing here ever writes outside this worktree.
"""

from __future__ import annotations

from iaso.paths import state_dir

import json
import os
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from iaso.awareness import gitfiles

VERSION = 1
CHANGING = "changing.json"
LANDED = "awareness-landed.json"
LANDED_MAX = 256
GIT_TIMEOUT_S = 2.0


def changing_path(root: Path) -> Path:
    return state_dir(Path(root)) / "cache" / CHANGING


def read_changing(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("v") == VERSION else None


def _write(path: Path, data: Mapping[str, Any]) -> None:
    """Atomic: a reader in another worktree sees the old file or the new one, never half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_branch(core: Any) -> str:
    """``merge.default_base`` (``main``), the base every branch is compared with: from the
    config when it carries the section, else from the parsed config cache (no YAML on the
    prompt path), else ``iaso.boundary.cli.merge_settings``. Remembered per core."""
    known = getattr(core, "_iaso_default_branch", None)
    if isinstance(known, str):
        return known
    name = _default_branch(core)
    try:
        core._iaso_default_branch = name
    except (AttributeError, TypeError):
        pass
    return name


def _default_branch(core: Any) -> str:
    section = getattr(getattr(core, "config", None), "merge", None)
    value = getattr(section, "default_base", None) if section is not None else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    root = state_dir(Path(core.root))
    try:
        config = root / "config.yaml"
        stat = config.stat()
    except OSError:
        return "main"       # no config at all: not a iaso repository
    try:
        cached = json.loads((root / "cache" / "config.json").read_text(encoding="utf-8"))
        if cached.get("key") == f"{stat.st_size}:{stat.st_mtime_ns}":
            merge = (cached.get("data") or {}).get("merge")
            base = merge.get("default_base") if isinstance(merge, dict) else None
            if isinstance(base, str) and base.strip():
                return base.strip()
    except (OSError, ValueError, AttributeError):
        pass
    try:
        from iaso.boundary.cli import merge_settings

        return str(merge_settings(core)["default_base"])
    except Exception:  # noqa: BLE001 - a broken config keeps the default
        return "main"


def _git(root: Path, *args: str) -> str | None:
    import subprocess  # here: the post-edit hook imports this module and must stay light

    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def committed_changes(root: Path, default: str, head: str | None
                      ) -> tuple[str | None, list[str], list[str]]:
    """``(base, paths, added)``: what the branch at ``root`` changed since its merge base
    with ``default`` (two git processes); nothing on the default branch itself."""
    if not head:
        return None, [], []
    base = _git(root, "merge-base", default, head)
    base = base.strip() if base else None
    if not base or base == head:
        return base or head, [], []
    out = _git(root, "diff", "--name-status", "--no-renames", "-z", base, head)
    paths: list[str] = []
    added: list[str] = []
    parts = (out or "").split("\0")
    for status, path in zip(parts[0::2], parts[1::2], strict=False):
        if not path:
            continue
        paths.append(path)
        if status.startswith("A"):
            added.append(path)
    return base, sorted(paths), sorted(added)


def changed_records(core: Any, paths: Iterable[str], added: Iterable[str] = ()
                    ) -> dict[str, dict[str, str]]:
    """``{id: {title, hash, how}}`` for the records ``paths`` change: ``edited`` or ``new``
    (the record's own file), ``ends`` (one of its link ends)."""
    paths = sorted(set(paths))
    if not paths:
        return {}
    index = core.index()
    added_set = set(added)
    by_path = core.records_for_paths(paths)
    out: dict[str, dict[str, str]] = {}
    for path in paths:
        for record_id in by_path.get(path, ()):
            record = index.get(record_id)
            if record is None:
                continue
            if record.path == path:
                how = "new" if path in added_set else "edited"
            else:
                how = "ends"
            previous = out.get(record_id)
            if previous is not None and previous["how"] != "ends":
                continue
            out[record_id] = {"title": record.title, "hash": record.hash, "how": how}
    return out


def tip(root: Path, branch: str) -> str | None:
    """The commit ``branch`` names, from git's files (no git process)."""
    common = gitfiles.common_dir(root)
    return gitfiles.resolve_ref(common, f"refs/heads/{branch}") if common is not None else None


def landed(root: Path, data: Mapping[str, Any], default_tip: str | None, *,
           allow_git: bool = False) -> bool:
    """Whether a worktree's published ``changing.json`` (``data``) describes a branch the
    default branch (now at ``default_tip``) has taken whole since: its ``head`` is reachable
    from the default tip, so nothing it committed is in flight any more (R17). Known without
    git when the default tip has not moved since it published; otherwise ``contains``."""
    head = str(data.get("head") or "")
    if (not head or not default_tip or not data.get("committed")
            or data.get("default_head") == default_tip):
        return False
    return contains(root, head, default_tip, allow_git=allow_git)


def contains(root: Path, head: str | None, default_tip: str | None, *,
             allow_git: bool = False) -> bool:
    """Whether the default branch (at ``default_tip``) holds the commit ``head``: from a
    cache keyed by the two commits, learned with ``allow_git`` (one ``git merge-base
    --is-ancestor``); unknown without it reads as False."""
    if not head or not default_tip:
        return False
    if head == default_tip:
        return True
    cache = state_dir(Path(root)) / "cache" / LANDED
    try:
        known = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    known = known if isinstance(known, dict) else {}
    key = f"{head}:{default_tip}"
    if key not in known:
        if not allow_git:
            return False
        import subprocess

        try:
            code = subprocess.run(["git", "merge-base", "--is-ancestor", head, default_tip],
                                  cwd=root, capture_output=True,
                                  timeout=GIT_TIMEOUT_S).returncode
        except (OSError, subprocess.SubprocessError):
            return False
        if code not in (0, 1):
            return False
        known = dict(list(known.items())[-(LANDED_MAX - 1):])
        known[key] = code == 0
        try:
            _write(cache, known)
        except OSError:
            pass
    return bool(known.get(key))


def moved_since(data: Mapping[str, Any], branch: str | None, head: str | None) -> bool:
    """Whether a worktree is no longer where its ``changing.json`` (``data``) describes it:
    its branch or its HEAD (read from git's files) changed since it published: a commit or a
    checkout no session saw, so what it listed (its pending edits included) is history."""
    published = str(data.get("head") or "")
    if data.get("branch") and branch and data.get("branch") != branch:
        return True
    return bool(published and head and published != head)


def publish(core: Any, changed_paths: Sequence[str], *, head_moved: bool | None = None
            ) -> dict[str, Any] | None:
    """Write this worktree's ``changing.json``; returns what it holds (None outside git).

    ``head_moved`` None: compare with the ``head`` the file holds. The committed part is
    recomputed only when HEAD moved (the pending paths restart from ``changed_paths``) or
    the default branch's tip moved (a merge of this branch empties it); otherwise
    ``changed_paths`` join the pending paths. The file is rewritten only when its content
    changed."""
    root = Path(core.root)
    me = gitfiles.current(root)
    if me is None:
        return None
    path = changing_path(root)
    old = read_changing(path) or {}
    default = default_branch(core)
    default_head = tip(root, default)
    moved = head_moved if head_moved is not None else (
        old.get("head") != me.head or "committed" not in old
        or old.get("branch") != me.branch)
    if moved or old.get("default_head") != default_head:
        # HEAD moved, or the default branch did (it may have merged this branch: then the
        # merge base is HEAD and nothing committed is in flight any more, R17)
        if me.branch == default:
            base, committed, added = me.head, [], []
        else:
            base, committed, added = committed_changes(root, default, me.head)
        pending = (sorted(set(changed_paths)) if moved else
                   sorted(set(old.get("pending") or []) | set(changed_paths)))
    else:
        base = old.get("base")
        committed = list(old.get("committed") or [])
        added = list(old.get("added") or [])
        pending = sorted(set(old.get("pending") or []) | set(changed_paths))
    paths = sorted(set(committed) | set(pending))
    data: dict[str, Any] = {
        "v": VERSION, "worktree": root.resolve().as_posix(), "branch": me.branch,
        "head": me.head, "default_head": default_head, "base": base,
        "committed": committed, "added": added,
        "pending": pending, "paths": paths,
        "records": changed_records(core, paths, added)}
    if {k: v for k, v in old.items() if k != "at"} == data:
        return old
    data["at"] = _now()
    _write(path, data)
    return data


def note_edit(paths: Any, path: str) -> None:
    """The post-edit hook: append one edited path to ``pending`` (no index, no git), so
    another session sees an edit before the turn ends. ``paths`` is a ``IasoPaths`` or the
    repository root."""
    root = Path(paths) if isinstance(paths, (str, os.PathLike)) else Path(paths.root)
    target = changing_path(root)
    data = read_changing(target)
    if data is None:
        data = {"v": VERSION, "worktree": root.resolve().as_posix(), "pending": [],
                "paths": [], "records": {}}
    pending = list(data.get("pending") or [])
    if path in pending:
        return
    pending.append(path)
    data["pending"] = sorted(pending)
    data["paths"] = sorted(set(data.get("paths") or []) | {path})
    data["at"] = _now()
    try:
        _write(target, data)
    except OSError:
        pass
