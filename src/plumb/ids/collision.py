"""ID collisions: two different records holding one ID (sp6 5.1; SR-072).

1. An in-progress merge leaves a record path unmerged because both sides added it
   (``git ls-files -u``: stages 2 and 3, no stage 1).
2. The working tree holds two record files declaring the same ``id`` at different paths.
3. ``preview(core, ref)``: records added on both ``HEAD`` and ``ref`` since their merge base
   with the same ID and different content (read only).

Two files with the same ID and the same content are not a collision.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import Collision

RECORD_PATH = re.compile(r"^\.plumb/(intents|requirements|decisions|features|ncs)/[^/]+\.md$")
_DUPLICATE = re.compile(r"^duplicate id (\S+): (.+) and (.+)$")
_TITLE = re.compile(r"^title:\s*(.*)$", re.MULTILINE)
_ID_LINE = re.compile(r"^id:\s*['\"]?([A-Z]+-\d+)", re.MULTILINE)


def git(root: Path, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, input=data, capture_output=True)


def blobs(root: Path, names: Sequence[str]) -> list[str | None]:
    """The text of each object name (``:2:path``, ``HEAD:path``, an oid), None when it does
    not exist; one ``cat-file --batch``."""
    if not names:
        return []
    result = git(root, "cat-file", "--batch", data="".join(f"{n}\n" for n in names).encode())
    out: list[str | None] = []
    rest = result.stdout
    for _ in names:
        header, _, rest = rest.partition(b"\n")
        parts = header.split()
        if len(parts) != 3 or parts[1] != b"blob":
            out.append(None)
            continue
        size = int(parts[2])
        out.append(rest[:size].decode("utf-8", "replace"))
        rest = rest[size + 1:]
    return out


def title_of(text: str | None) -> str:
    """The record's title (frontmatter ``title``) read without YAML, for the owner's
    terms; "" when absent."""
    if not text:
        return ""
    from plumb.ids.rewrite import parse

    parsed = parse(text)
    if parsed is not None and isinstance(parsed[0].get("title"), str):
        return parsed[0]["title"]
    match = _TITLE.search(text)
    return match.group(1).strip().strip("'\"") if match else ""


def id_of(text: str | None, path: str) -> str:
    match = _ID_LINE.search(text or "")
    return match.group(1) if match else Path(path).stem


def unmerged_add_add(root: Path) -> list[Collision]:
    """Record paths both sides added (stages 2 and 3 without 1) with different content."""
    result = git(root, "ls-files", "-u", "-z", "--", ".plumb/")
    if result.returncode != 0 or not result.stdout:
        return []
    stages: dict[str, dict[int, str]] = {}
    for entry in result.stdout.decode("utf-8", "replace").split("\0"):
        if not entry.strip():
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and RECORD_PATH.match(path):
            stages.setdefault(path, {})[int(parts[2])] = parts[1]
    out: list[Collision] = []
    for path, found in sorted(stages.items()):
        if 1 in found or 2 not in found or 3 not in found or found[2] == found[3]:
            continue
        ours, theirs = blobs(root, [found[2], found[3]])
        out.append(Collision(id=id_of(ours, path), paths=(path,),
                             sides=(title_of(ours), title_of(theirs)), how="add/add"))
    return out


def duplicates(core: Any) -> list[Collision]:
    """Two record files declaring one ID in the working tree (``Store.problems``), the
    first parent's file first."""
    out: list[Collision] = []
    for problem in core.store.problems():
        match = _DUPLICATE.match(problem)
        if not match:
            continue
        record_id, first, second = match.groups()
        paths = [first, second]
        texts = {}
        for path in paths:
            try:
                texts[path] = (Path(core.root) / path).read_text(encoding="utf-8")
            except OSError:
                texts[path] = ""
        if texts[first] == texts[second]:
            continue
        paths = kept_first(core.root, paths)
        out.append(Collision(id=record_id, paths=tuple(paths),
                             sides=tuple(title_of(texts[p]) for p in paths), how="duplicate"))
    return out


def kept_first(root: Path, paths: list[str]) -> list[str]:
    """Order two paths so the one that keeps its ID comes first (DEC-022): the one in the
    first parent (``HEAD``, or ``HEAD^1`` of a merge commit), else the earlier added."""
    for parent in ("HEAD", "HEAD^1"):
        present = [p for p, text in zip(paths, blobs(root, [f"{parent}:{p}" for p in paths]),
                                        strict=True) if text is not None]
        if len(present) == 1:
            return [present[0]] + [p for p in paths if p != present[0]]
    added = []
    for path in paths:
        stamp = git(root, "log", "--diff-filter=A", "--format=%ct", "-1", "--", path)
        text = stamp.stdout.decode().strip()
        added.append((int(text) if text.isdigit() else 1 << 62, path))
    return [p for _, p in sorted(added)]


def collisions(core: Any, base: str | None = None) -> tuple[Collision, ...]:
    """Every ID collision of the working tree (sections 1 and 2 of 5.1). ``base`` is
    accepted for the merge report's signature; the working tree is what is checked."""
    del base
    return tuple(unmerged_add_add(Path(core.root)) + duplicates(core))


def preview(core: Any, ref: str) -> tuple[Collision, ...]:
    """Records added on both ``HEAD`` and ``ref`` since their merge base with the same ID
    and different content: what merging ``ref`` would bring (read only)."""
    root = Path(core.root)
    base = git(root, "merge-base", "HEAD", ref)
    if base.returncode != 0:
        return ()
    fork = base.stdout.decode().strip()

    def added(tip: str) -> set[str]:
        result = git(root, "diff", "--name-only", "--diff-filter=A", "-z", fork, tip, "--",
                     ".plumb/")
        return {p for p in result.stdout.decode("utf-8", "replace").split("\0")
                if RECORD_PATH.match(p)}

    both = sorted(added("HEAD") & added(ref))
    out: list[Collision] = []
    for path in both:
        ours, theirs = blobs(root, [f"HEAD:{path}", f"{ref}:{path}"])
        if ours == theirs:
            continue
        out.append(Collision(id=id_of(ours, path), paths=(path,),
                             sides=(title_of(ours), title_of(theirs)), how="preview"))
    return tuple(out)
