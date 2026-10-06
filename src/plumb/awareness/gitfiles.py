"""git's own files, read without running git (sp6 9.3, SR-079).

The awareness read runs inside the prompt hook, where no git process may start: the common
git directory, the worktrees, the branch tips and a loose object are all plain files. A path
that does not exist (a removed worktree, a packed ref, a packed object) is skipped, never an
error. Standard library only.
"""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass
from pathlib import Path

ZERO_OID = "0" * 40


@dataclass(frozen=True)
class Worktree:
    """One checkout of the repository: its directory, its git directory, its branch (None
    when HEAD is detached) and the commit HEAD names (None when unborn or unknown)."""

    path: Path
    gitdir: Path
    branch: str | None
    head: str | None
    main: bool = False


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def git_dir(root: Path) -> Path | None:
    """The git directory of the checkout at ``root``: ``.git`` itself, or the directory a
    ``.git`` file names (``gitdir: ...``, a linked worktree)."""
    dot = Path(root) / ".git"
    if dot.is_dir():
        return dot
    text = _read(dot)
    if not text or not text.startswith("gitdir:"):
        return None
    target = Path(text[len("gitdir:"):].strip())
    if not target.is_absolute():
        target = Path(root) / target
    return target if target.is_dir() else None


def common_dir(root: Path) -> Path | None:
    """The common git directory every worktree shares (refs, objects, ``worktrees/``)."""
    gitdir = git_dir(root)
    if gitdir is None:
        return None
    text = _read(gitdir / "commondir")
    if not text:
        return gitdir
    common = Path(text)
    if not common.is_absolute():
        common = gitdir / common
    return Path(os.path.normpath(common))


def _packed_refs(common: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    text = _read(common / "packed-refs")
    for line in (text or "").splitlines():
        if not line or line[0] in "#^":
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and len(parts[0]) >= 40:
            out[parts[1].strip()] = parts[0]
    return out


def resolve_ref(common: Path, name: str) -> str | None:
    """The object a ref names (a loose ref file wins over ``packed-refs``)."""
    text = _read(common / name)
    if text and not text.startswith("ref:") and len(text) >= 40:
        return text.split()[0]
    return _packed_refs(common).get(name)


def _head(gitdir: Path, common: Path) -> tuple[str | None, str | None]:
    text = _read(gitdir / "HEAD")
    if not text:
        return None, None
    if text.startswith("ref:"):
        ref = text[4:].strip()
        branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else None
        return branch, resolve_ref(common, ref)
    return None, text.split()[0] if len(text) >= 40 else None


def current(root: Path) -> Worktree | None:
    """This checkout as a ``Worktree``; None outside git."""
    gitdir = git_dir(root)
    common = common_dir(root)
    if gitdir is None or common is None:
        return None
    branch, head = _head(gitdir, common)
    return Worktree(Path(root), gitdir, branch, head, main=gitdir == common)


def worktrees(root: Path) -> list[Worktree]:
    """Every checkout of the repository ``root`` belongs to, ``root``'s own included: the
    main worktree (the common directory's parent, unless the repository is bare) and each
    ``worktrees/*`` entry whose directory still exists (SR-079 EX-4)."""
    common = common_dir(root)
    if common is None:
        return []
    out: list[Worktree] = []
    if common.name == ".git" and (common.parent / ".git").exists():
        branch, head = _head(common, common)
        out.append(Worktree(common.parent, common, branch, head, main=True))
    try:
        entries = sorted(p for p in (common / "worktrees").iterdir() if p.is_dir())
    except OSError:
        entries = []
    for entry in entries:
        pointer = _read(entry / "gitdir")
        if not pointer:
            continue
        path = Path(pointer)
        path = path.parent if path.name == ".git" else path
        if not (path / ".git").exists():
            continue  # a removed worktree whose entry git has not pruned yet
        branch, head = _head(entry, common)
        out.append(Worktree(path, entry, branch, head))
    return out


def branch_tips(common: Path) -> dict[str, str]:
    """``{branch: tip}`` for every local branch: loose files under ``refs/heads`` (which win)
    and ``packed-refs``."""
    tips = {name.removeprefix("refs/heads/"): oid for name, oid in _packed_refs(common).items()
            if name.startswith("refs/heads/")}
    heads = common / "refs" / "heads"
    for dirpath, _dirs, files in os.walk(heads):
        for name in files:
            path = Path(dirpath) / name
            text = _read(path)
            if text and len(text) >= 40:
                tips[path.relative_to(heads).as_posix()] = text.split()[0]
    return tips


def ref_mtime(common: Path, branch: str) -> float:
    """When a branch's loose ref last moved (0 for a packed one): newest first in scans."""
    try:
        return (common / "refs" / "heads" / branch).stat().st_mtime
    except OSError:
        return 0.0


def same_path(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except OSError:
        return False


def read_loose_object(common: Path, oid: str) -> tuple[str, bytes] | None:
    """``(type, content)`` of a loose object, or None when it is packed or missing: the
    caller then asks git, off the prompt path."""
    if not oid or len(oid) < 40:
        return None
    try:
        raw = zlib.decompress((common / "objects" / oid[:2] / oid[2:]).read_bytes())
    except (OSError, zlib.error):
        return None
    head, sep, body = raw.partition(b"\0")
    if not sep:
        return None
    kind, _, _size = head.decode("ascii", "replace").partition(" ")
    return kind, body
