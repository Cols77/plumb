"""The shared ref ``refs/iaso/ids`` (sp6 4.1): read it, and move it by compare-and-swap.

The ref points to a blob of canonical JSON ``{"v": 1, "high": {prefix: n}, "recent": [...]}``.
Refs outside ``refs/worktree/`` are shared by every worktree of a repository, so one ref
serves them all; git's own ``update-ref <ref> <new> <old>`` is the only writer, and it fails
when the ref no longer holds ``<old>``. The ref is local to the clone: never pushed or
fetched. ``ids`` alone moves it (sp6 plan 3.1).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REF = "refs/iaso/ids"
SCHEMA = 1
RECENT_MAX = 50


class NoGit(RuntimeError):
    """The root is not inside a git work tree, or git cannot run."""


class Moved(RuntimeError):
    """``update-ref`` refused: the ref no longer holds the value it was read with."""


def git(root: Path, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, input=data, capture_output=True)
    except OSError as exc:  # git missing, or the root is gone
        raise NoGit(str(exc)) from exc


def canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8") + b"\n"


def empty() -> dict[str, Any]:
    return {"v": SCHEMA, "high": {}, "recent": []}


def _parse(blob: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return empty()
    if not isinstance(raw, dict):
        return empty()
    high = raw.get("high") if isinstance(raw.get("high"), dict) else {}
    recent = raw.get("recent") if isinstance(raw.get("recent"), list) else []
    return {"v": SCHEMA,
            "high": {str(k): int(v) for k, v in high.items()
                     if isinstance(v, int) and not isinstance(v, bool)},
            "recent": [r for r in recent if isinstance(r, dict)][-RECENT_MAX:]}


def read(root: Path) -> tuple[str | None, dict[str, Any]]:
    """``(oid, data)`` of the ref, ``(None, empty)`` when it does not exist yet. One git
    process (``cat-file --batch`` prints the blob's oid with its content). Raises ``NoGit``
    outside a git work tree."""
    result = git(root, "cat-file", "--batch", data=f"{REF}\n".encode())
    if result.returncode != 0:
        raise NoGit(result.stderr.decode("utf-8", "replace").strip() or "not a git repository")
    header, _, rest = result.stdout.partition(b"\n")
    parts = header.decode("utf-8", "replace").split()
    if len(parts) != 3 or parts[1] != "blob":
        return None, empty()  # "<ref> missing"
    size = int(parts[2])
    return parts[0], _parse(rest[:size])


def update(root: Path, data: Mapping[str, Any], old: str | None, message: str) -> str:
    """Write ``data`` as a blob and move the ref from ``old`` to it (create only when
    ``old`` is None). Returns the new oid; raises ``Moved`` when the swap failed."""
    blob = git(root, "hash-object", "-w", "--stdin", data=canonical(data))
    if blob.returncode != 0:
        raise NoGit(blob.stderr.decode("utf-8", "replace").strip())
    new = blob.stdout.decode().strip()
    expected = old if old is not None else "0" * len(new)
    moved = git(root, "update-ref", "-m", message, REF, new, expected)
    if moved.returncode != 0:
        raise Moved(moved.stderr.decode("utf-8", "replace").strip())
    return new


def branch(root: Path) -> str:
    """The checked-out branch name, or "HEAD" when detached (for ``recent`` only)."""
    result = git(root, "symbolic-ref", "-q", "--short", "HEAD")
    name = result.stdout.decode("utf-8", "replace").strip()
    return name if result.returncode == 0 and name else "HEAD"
