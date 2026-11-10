"""ID collisions: two different records holding one ID (sp6 5.1; SR-072).

1. An in-progress merge leaves a record path unmerged because both sides added it
   (``git ls-files -u``: stages 2 and 3, no stage 1).
2. The working tree holds two record files declaring the same ``id`` at different paths.
3. A merge (in progress, or a merge commit at or after ``base``) whose two parents both added
   one record path since their merge base as two records, resolved by hand to a
   single file (``kept-one``): the other record is lost from the tree, so the path is still
   a collision until ``iaso merge-fix`` renumbers the incoming record (its ``renumber``
   event names it). Every entry point (``iaso check --merge``, ``iaso merge-check``, the
   pre-push hook, ``iaso merge-fix``) reads collisions through ``collisions`` only.
4. ``preview(core, ref)``: records added on both ``HEAD`` and ``ref`` since their merge base
   with the same ID holding two records (read only).

Two files with the same ID holding the same record are not a collision: "the same" is
``same_record``, the one comparison every check above makes. It compares record hashes
(concept 4.4: every field but ``links``), so a side that only linked or repinned the
record, or a merge-driver resolution equal after parsing (7.5), is one record, not two.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from iaso.contracts import Collision

RECORD_PATH = re.compile(r"^\.iaso/(intents|requirements|decisions|features|ncs)/[^/]+\.md$")
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
    from iaso.ids.rewrite import parse

    parsed = parse(text)
    if parsed is not None and isinstance(parsed[0].get("title"), str):
        return parsed[0]["title"]
    match = _TITLE.search(text)
    return match.group(1).strip().strip("'\"") if match else ""


def id_of(text: str | None, path: str) -> str:
    match = _ID_LINE.search(text or "")
    return match.group(1) if match else Path(path).stem


def unmerged_add_add(root: Path) -> list[Collision]:
    """Record paths both sides added (stages 2 and 3 without 1) holding two records."""
    result = git(root, "ls-files", "-u", "-z", "--", ".iaso/")
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
        if same_record(ours, theirs):
            continue
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
        if same_record(texts[first], texts[second]):
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


def _added(root: Path, fork: str, tip: str) -> set[str]:
    """Record paths ``tip`` added since ``fork``."""
    result = git(root, "diff", "--name-only", "--diff-filter=A", "--no-renames", "-z", fork,
                 tip, "--", ".iaso/")
    return {p for p in result.stdout.decode("utf-8", "replace").split("\0")
            if RECORD_PATH.match(p)}


def _rev(root: Path, name: str) -> str | None:
    result = git(root, "rev-parse", "-q", "--verify", f"{name}^{{commit}}")
    return result.stdout.decode().strip() or None if result.returncode == 0 else None


def merges(root: Path, base: str | None) -> list[tuple[str, str]]:
    """``(first parent, incoming parent)`` of the merge in progress (``MERGE_HEAD``) and of
    every merge commit after ``base`` (``base..HEAD``); without ``base``, the merge in
    progress, else ``HEAD`` when it is a merge commit (the pair ``iaso merge-fix`` fixes)."""
    out: list[tuple[str, str]] = []
    merge_head = _rev(root, "MERGE_HEAD")
    if merge_head:
        out.append(("HEAD", merge_head))
    if base is None:
        second = None if merge_head else _rev(root, "HEAD^2")
        if second:
            out.append(("HEAD^1", second))
        return out
    listed = git(root, "rev-list", "--merges", "--parents", f"{base}..HEAD")
    for line in listed.stdout.decode().splitlines():
        parts = line.split()
        out.extend((parts[1], other) for other in parts[2:])
    return out


def renumbered(core: Any) -> set[tuple[str, str]]:
    """``(old id, incoming record hash)`` of every ``renumber`` event: the collisions
    ``iaso merge-fix`` already fixed."""
    out: set[tuple[str, str]] = set()
    for entry in core.events():
        if entry.kind == "renumber":
            old, pinned = entry.payload.get("from"), entry.payload.get("old_hash")
            if isinstance(old, str) and isinstance(pinned, str):
                out.add((old, pinned))
    return out


def _hash(text: str) -> str | None:
    from iaso.ids.rewrite import parse
    from iaso.model import record_hash

    parsed = parse(text)
    return record_hash(parsed[0], parsed[1]) if parsed is not None else None


def same_record(first: str | None, second: str | None) -> bool:
    """Whether two record files' texts hold one record (5.1): equal record hashes, which
    leave ``links`` (and their pins) out (concept 4.4); equal text when either does not
    parse. The one "same content" test of ``unmerged_add_add``, ``duplicates``,
    ``kept_one`` and ``preview``."""
    if first == second:
        return True
    if first is None or second is None:
        return False
    first_hash = _hash(first)
    return first_hash is not None and first_hash == _hash(second)


def kept_one(core: Any, base: str | None, reported: set[str]) -> list[Collision]:
    """Record paths both parents of a merge added as two records that the merge
    resolved to one file, unless a ``renumber`` already moved the incoming record."""
    root = Path(core.root)
    pairs = merges(root, base)
    if not pairs:
        return []
    fixed = renumbered(core)
    out: list[Collision] = []
    seen = set(reported)
    for ours, theirs in pairs:
        fork = git(root, "merge-base", ours, theirs)
        if fork.returncode != 0:
            continue
        start = fork.stdout.decode().strip()
        both = sorted((_added(root, start, ours) & _added(root, start, theirs)) - seen)
        if not both:
            continue
        texts = blobs(root, [f"{side}:{p}" for p in both for side in (ours, theirs)])
        for n, path in enumerate(both):
            kept, incoming = texts[2 * n], texts[2 * n + 1]
            if kept is None or incoming is None or same_record(kept, incoming):
                continue
            if (id_of(incoming, path), _hash(incoming)) in fixed:
                continue
            seen.add(path)
            out.append(Collision(id=id_of(kept, path), paths=(path,),
                                 sides=(title_of(kept), title_of(incoming)), how="kept-one"))
    return out


def collisions(core: Any, base: str | None = None) -> tuple[Collision, ...]:
    """Every ID collision of the merge result (5.1): unmerged add/add paths, two files with
    one ID in the working tree, and add/add paths a merge (in progress, or committed after
    ``base``; without ``base``, ``HEAD``'s) resolved to a single file."""
    root = Path(core.root)
    unmerged = unmerged_add_add(root)
    found = unmerged + duplicates(core)
    return tuple(found + kept_one(core, base, {c.paths[0] for c in unmerged}))


def preview(core: Any, ref: str) -> tuple[Collision, ...]:
    """Records added on both ``HEAD`` and ``ref`` since their merge base with the same ID
    holding two records: what merging ``ref`` would bring (read only)."""
    root = Path(core.root)
    base = git(root, "merge-base", "HEAD", ref)
    if base.returncode != 0:
        return ()
    fork = base.stdout.decode().strip()

    def added(tip: str) -> set[str]:
        result = git(root, "diff", "--name-only", "--diff-filter=A", "-z", fork, tip, "--",
                     ".iaso/")
        return {p for p in result.stdout.decode("utf-8", "replace").split("\0")
                if RECORD_PATH.match(p)}

    both = sorted(added("HEAD") & added(ref))
    out: list[Collision] = []
    for path in both:
        ours, theirs = blobs(root, [f"HEAD:{path}", f"{ref}:{path}"])
        if same_record(ours, theirs):
            continue
        out.append(Collision(id=id_of(ours, path), paths=(path,),
                             sides=(title_of(ours), title_of(theirs)), how="preview"))
    return tuple(out)
