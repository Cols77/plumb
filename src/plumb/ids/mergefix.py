"""``plumb merge-fix`` (sp6 5; SR-071, DEC-022).

The first parent (the branch being merged into) keeps its IDs. The incoming record (stage 3,
``MERGE_HEAD``'s side) gets a new ID from ``ids.reserve`` after ``ids.observe`` has raised
the ref over every ID both sides hold; every reference the incoming side introduced is
rewritten (``rewrite``), pins stale only because of the new ID are repinned, one ``renumber``
event maps the incoming approvals and commit trailers, and the result is staged during a
merge. It never commits and never rewrites history; a second run finds nothing to fix.
Renumbering changes no intent, so it never asks the owner.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.contracts import Collision, MergeFixResult
from plumb.ids import collision as _collision
from plumb.ids import rewrite
from plumb.ids.reservation import DIRS, fmt, highest, prefix_of, split

KIND_OF_PREFIX = {"INT": "intent", "SR": "requirement", "DEC": "decision", "FEAT": "feature",
                  "NC": "nc"}


@dataclass
class _Context:
    """The three sides of the merge the incoming record came with."""

    merging: bool = False                 # MERGE_HEAD exists: stage what changes
    base: str | None = None               # the merge base
    ours: str | None = None               # the first parent
    theirs: str | None = None             # the incoming side's tip


@dataclass
class _Plan:
    collision: Collision
    old: str
    kind: str
    title: str
    incoming_text: str                    # the incoming record file's text
    incoming_path: str                    # where it is now (the shared path for add/add)
    kept_text: str | None = None          # add/add: the first parent's file, restored
    new: str = ""
    new_path: str = ""
    references: int = 0
    files: set[str] = field(default_factory=set)
    old_hash: str = ""
    new_hash: str = ""
    approvals: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True)


def _out(root: Path, *args: str) -> str | None:
    result = _git(root, *args)
    return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else None


def context(root: Path) -> _Context:
    merge_head = _out(root, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    if merge_head:
        return _Context(merging=True, base=_out(root, "merge-base", "HEAD", merge_head),
                        ours="HEAD", theirs=merge_head)
    second = _out(root, "rev-parse", "-q", "--verify", "HEAD^2")
    if second:  # the merge was already committed: fix it in the working tree
        return _Context(merging=False, base=_out(root, "merge-base", "HEAD^1", "HEAD^2"),
                        ours="HEAD^1", theirs=second)
    return _Context()


def _plan(core: Any, found: Collision, ctx: _Context) -> _Plan | None:
    root = Path(core.root)
    if found.how == "add/add":
        path = found.paths[0]
        kept, incoming = _collision.blobs(root, [f":2:{path}", f":3:{path}"])
        if kept is None or incoming is None or rewrite.parse(incoming) is None:
            return None
        return _Plan(found, found.id, KIND_OF_PREFIX.get(found.id.split("-")[0], ""),
                     _collision.title_of(incoming), incoming, path, kept_text=kept)
    if found.how == "kept-one":  # resolved to one file by hand: restore the incoming record
        if not (ctx.ours and ctx.theirs):
            return None
        path = found.paths[0]
        first, incoming = _collision.blobs(root, [f"{ctx.ours}:{path}", f"{ctx.theirs}:{path}"])
        try:
            current: str | None = (root / path).read_bytes().decode("utf-8", "replace")
        except OSError:
            current = None
        # the first parent keeps the ID (DEC-022): the resolved text, unless it is the
        # incoming record's, in which case the first parent's own text
        kept = current if current is not None and current != incoming else first
        if kept is None or incoming is None or rewrite.parse(incoming) is None:
            return None
        return _Plan(found, found.id, KIND_OF_PREFIX.get(found.id.split("-")[0], ""),
                     _collision.title_of(incoming), incoming, path, kept_text=kept)
    if len(found.paths) != 2:
        return None
    incoming_path = found.paths[1]  # kept_first ordered the first parent's file first
    try:
        text = (root / incoming_path).read_text(encoding="utf-8")
    except OSError:
        return None
    if rewrite.parse(text) is None:
        return None
    return _Plan(found, found.id, KIND_OF_PREFIX.get(found.id.split("-")[0], ""),
                 _collision.title_of(text), text, incoming_path)


def _held_ids(core: Any, ctx: _Context) -> list[str]:
    """Every ID both sides hold: this tree's records and the incoming tip's record files."""
    held = list(core.index())
    if ctx.theirs:
        listed = _out(Path(core.root), "ls-tree", "-r", "--name-only", ctx.theirs, "--",
                      ".plumb/")
        for name in (listed or "").splitlines():
            stem = Path(name).stem
            if split(stem) is not None:
                held.append(stem)
    return held


def _assign(core: Any, plans: list[_Plan], held: Sequence[str], dry_run: bool) -> None:
    from plumb import ids

    if dry_run:
        top = highest(held)
        for plan in plans:
            prefix = prefix_of(plan.kind)
            peeked = split(ids.peek(core.paths, plan.kind, local=held))
            number = max(top.get(prefix, 0) + 1, peeked[1] if peeked else 1)
            top[prefix] = number
            plan.new = fmt(prefix, number)
    else:
        ids.observe(core.paths, held)
        for plan in plans:
            plan.new = ids.reserve(core.paths, plan.kind, local=held)[0]
    for plan in plans:
        plan.new_path = f".plumb/{DIRS[plan.new.split('-')[0]]}/{plan.new}.md"


def _candidates(root: Path, ctx: _Context, skip: set[str]) -> list[str]:
    """Files the incoming side changed since the merge base that may hold references."""
    if not (ctx.base and ctx.theirs):
        return []
    listed = _git(root, "diff", "--name-only", "-z", "--no-renames", ctx.base, ctx.theirs)
    out = []
    for path in listed.stdout.decode("utf-8", "replace").split("\0"):
        if not path or path in skip:
            continue
        if _collision.RECORD_PATH.match(path) or path == ".plumb/claims.yaml" or \
                path.endswith(".py"):
            out.append(path)
    return out


def _unresolved(root: Path, ctx: _Context, olds: Sequence[str], skip: set[str]) -> list[str]:
    """The files the rewrite would have to read but cannot: a candidate whose incoming
    version names a renumbered ID and that is still unmerged (``git ls-files -u``), or whose
    merged text does not read (conflict markers, a broken record, test or claims file).
    Rewriting around them would leave an incoming reference on the first parent's record,
    so ``merge_fix`` renumbers nothing while any is left."""
    paths = _candidates(root, ctx, skip)
    if not paths:
        return []
    listed = _git(root, "ls-files", "-u", "-z")
    unmerged = {entry.partition("\t")[2]
                for entry in listed.stdout.decode("utf-8", "replace").split("\0") if entry}
    patterns = [rewrite.token(old) for old in olds]
    out = []
    for path, theirs in zip(paths, _collision.blobs(root, [f"{ctx.theirs}:{p}" for p in paths]),
                            strict=True):
        if theirs is None or not any(p.search(theirs) for p in patterns):
            continue
        if path.endswith(".py") and "mark.sr" not in theirs:
            continue
        if path in unmerged:
            out.append(path)
            continue
        full = root / path
        if not full.is_file():
            continue
        if not rewrite.readable(path, full.read_bytes().decode("utf-8", "replace")):
            out.append(path)
    return out


def _rewrite_others(core: Any, ctx: _Context, mapping: Mapping[str, str], skip: set[str],
                    before: dict[str, str], ends_before: dict[Any, str | None]
                    ) -> dict[str, int]:
    """Rewrite the references the incoming side introduced in every other file; returns
    ``{path: references}``. ``before`` gets each rewritten record's hash before the
    rewrite, ``ends_before`` the hash of every file, symbol or test-node link end inside a
    rewritten file (for ``_repin``)."""
    root = Path(core.root)
    changed: dict[str, int] = {}
    paths = _candidates(root, ctx, skip)
    if not paths:
        return changed
    names = [f"{side}:{p}" for p in paths for side in (ctx.base, ctx.ours, ctx.theirs)]
    texts = _collision.blobs(root, names)
    pending: dict[str, str] = {}
    for n, path in enumerate(paths):
        base, ours, theirs = texts[3 * n:3 * n + 3]
        full = root / path
        if theirs is None or not full.is_file():
            continue
        merged = full.read_bytes().decode("utf-8", "replace")
        if _collision.RECORD_PATH.match(path):
            new_text, count = rewrite.record(merged, base, ours, theirs, mapping)
        elif path == ".plumb/claims.yaml":
            new_text, count = rewrite.claims(merged, base, ours, theirs, mapping)
        else:
            if "mark.sr" not in theirs:
                continue
            new_text, count = rewrite.markers(merged, base, ours, theirs, mapping)
        if not count:
            continue
        changed[path] = count
        pending[path] = new_text
        if _collision.RECORD_PATH.match(path):
            parsed = rewrite.parse(merged)
            if parsed is not None:
                from plumb.model import record_hash

                before[str(parsed[0].get("id"))] = record_hash(parsed[0], parsed[1])
    if pending:
        from plumb.hashing import target_path

        core.store.invalidate()
        for record in core.index().values():
            for link in record.links:
                if link.target.record is None and target_path(link.target) in pending:
                    ends_before[link.target] = core.hash_target(link.target)
        for path, new_text in pending.items():
            (root / path).write_bytes(new_text.encode("utf-8"))
    return changed


def _trailer_files(root: Path) -> list[Path]:
    out = []
    for name in ("MERGE_MSG", "SQUASH_MSG"):
        path = _out(root, "rev-parse", "--git-path", name)
        if path:
            full = Path(path) if Path(path).is_absolute() else root / path
            if full.is_file():
                out.append(full)
    return out


def _repin(core: Any, before: Mapping[str, str],
           ends_before: Mapping[Any, str | None]) -> None:
    """Repin the pins that went stale only because an ID changed: a pin equal to an end's
    hash before the rewrite (a record, or a file, symbol or test node inside a rewritten
    file) moves to its hash after; any other stale pin is kept."""
    from plumb.model import link_to_dict

    core.store.invalidate()
    index = core.index()
    after = {rid: index[rid].hash for rid in before if rid in index}
    ends_after = {end: core.hash_target(end) for end in ends_before}
    for record in list(index.values()):
        links = [link_to_dict(link) for link in record.links]
        touched = False
        for parsed, link in zip(record.links, links, strict=True):
            pin = link.get("pin")
            if not isinstance(pin, dict):
                continue
            target = link.get("to")
            end = parsed.target
            if target in before and target in after and pin.get("to") == before[target] \
                    and after[target] != before[target]:
                pin["to"] = after[target]
                touched = True
            elif end in ends_before and ends_before[end] is not None and \
                    pin.get("to") == ends_before[end] and ends_after[end] is not None and \
                    ends_after[end] != ends_before[end]:
                pin["to"] = ends_after[end]
                touched = True
            if record.id in before and record.id in after and \
                    pin.get("from") == before[record.id] and after[record.id] != before[record.id]:
                pin["from"] = after[record.id]
                touched = True
        if touched:
            core.store.set_links(record.id, links)
    core.store.invalidate()


def _approvals(core: Any, old: str, old_hash: str) -> list[str]:
    """The valid approvals of ``old`` at the incoming content (its pinned hash)."""
    from plumb.confirm import checked

    out = []
    for entry, problem in checked(core):
        if problem is not None or entry.kind != "approval":
            continue
        for item in entry.payload.get("records") or []:
            if isinstance(item, Mapping) and item.get("id") == old and \
                    item.get("hash") == old_hash:
                out.append(entry.digest)
                break
    return out


def _commits(root: Path, ctx: _Context, old: str) -> list[str]:
    """The incoming commits since the merge base whose ``SR:`` trailer names ``old``."""
    from plumb.trailers import parse_sr_trailer

    if not (ctx.base and ctx.theirs):
        return []
    listed = _git(root, "log", "--format=%H%x1f%B%x1e", f"{ctx.base}..{ctx.theirs}")
    out = []
    for chunk in listed.stdout.decode("utf-8", "replace").split("\x1e"):
        sha, _, message = chunk.strip("\n").partition("\x1f")
        if sha and old in parse_sr_trailer(message):
            out.append(sha.strip())
    return out


def _lines(plans: Sequence[_Plan], remaining: Sequence[Collision], dry_run: bool) -> list[str]:
    from plumb.present import owner_text as text

    lines = []
    for plan in plans:
        if dry_run:
            lines.append(text.WOULD_RENUMBER.format(old=plan.old, title=plan.title,
                                                    new=plan.new))
            continue
        lines.append(text.RENUMBERED.format(
            old=plan.old, title=plan.title, new=plan.new, references=plan.references,
            files=len(plan.files),
            approval=text.APPROVAL_CARRIED if plan.approvals else text.APPROVAL_NONE,
            commits=len(plan.commits)))
    for found in remaining:
        lines.append(text.FIX_REMAINS.format(id=found.id, where=", ".join(found.sides)))
    return lines or [text.NOTHING_TO_FIX]


def merge_fix(core: Any, *, dry_run: bool = False,
              from_ref: str | None = None) -> MergeFixResult:
    from plumb.present import owner_text as text

    root = Path(core.root)
    if from_ref:
        found = _collision.preview(core, from_ref)
        lines = [text.PREVIEW.format(ref=from_ref, id=c.id, ours=c.sides[0],
                                     theirs=c.sides[1]) for c in found]
        return MergeFixResult(remaining=found, dry_run=True,
                              lines=tuple(lines or [text.NOTHING_TO_FIX]))
    found = _collision.collisions(core)
    if not found:
        return MergeFixResult(dry_run=dry_run, lines=(text.NOTHING_TO_FIX,))
    ctx = context(root)
    plans: list[_Plan] = []
    remaining: list[Collision] = []
    for item in found:
        plan = _plan(core, item, ctx)
        (plans.append(plan) if plan is not None else remaining.append(item))
    if not plans:
        return MergeFixResult(remaining=tuple(remaining), dry_run=dry_run,
                              lines=tuple(_lines([], remaining, dry_run)))
    blocked = _unresolved(root, ctx, [p.old for p in plans], {p.incoming_path for p in plans})
    if blocked:  # the one gate before any reservation or write, dry run included
        lines = [text.FIX_BLOCKED.format(id=p.old, title=p.title, files=len(blocked))
                 for p in plans]
        return MergeFixResult(remaining=tuple(found), blocked=tuple(blocked), dry_run=dry_run,
                              lines=tuple(lines))
    held = _held_ids(core, ctx) + [p.old for p in plans]
    _assign(core, plans, held, dry_run)
    mapping = {p.old: p.new for p in plans}
    if dry_run:
        return MergeFixResult(
            renumbered=tuple({"from": p.old, "to": p.new, "title": p.title, "kind": p.kind}
                             for p in plans),
            remaining=tuple(remaining), dry_run=True,
            lines=tuple(_lines(plans, remaining, True)))
    return _apply(core, ctx, plans, remaining, mapping)


def _apply(core: Any, ctx: _Context, plans: list[_Plan], remaining: list[Collision],
           mapping: Mapping[str, str]) -> MergeFixResult:
    from plumb.model import record_hash

    root = Path(core.root)
    before: dict[str, str] = {}
    staged: set[str] = set()
    for plan in plans:
        data, body = rewrite.parse(plan.incoming_text)  # type: ignore[misc]
        plan.old_hash = record_hash(data, body)
        before[plan.new] = plan.old_hash
        new_text, refs = rewrite.incoming_record(plan.incoming_text, mapping)
        plan.references += refs
        if refs:
            plan.files.add(plan.new_path)
        target = root / plan.new_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new_text.encode("utf-8"))
        if plan.kept_text is not None:  # add/add: the first parent's record keeps the path
            (root / plan.incoming_path).write_bytes(plan.kept_text.encode("utf-8"))
        else:
            (root / plan.incoming_path).unlink(missing_ok=True)
        staged |= {plan.new_path, plan.incoming_path}
    skip = {p.incoming_path for p in plans} | {p.new_path for p in plans}
    ends_before: dict[Any, str | None] = {}
    others = _rewrite_others(core, ctx, mapping, skip, before, ends_before)
    for path, count in others.items():
        owner = _owner_plan(plans, path, mapping, root)
        owner.references += count
        owner.files.add(path)
    staged |= set(others)
    for message_file in _trailer_files(root):
        text_in = message_file.read_bytes().decode("utf-8", "replace")
        text_out, count = rewrite.trailers(text_in, mapping)
        if count:
            message_file.write_bytes(text_out.encode("utf-8"))
    _repin(core, before, ends_before)
    index = core.index()
    for plan in plans:
        plan.new_hash = index[plan.new].hash if plan.new in index else ""
        plan.approvals = _approvals(core, plan.old, plan.old_hash)
        plan.commits = _commits(root, ctx, plan.old)
        core.log_append("events", "renumber", {
            "from": plan.old, "to": plan.new, "kind": plan.kind, "title": plan.title,
            "incoming": ctx.theirs if ctx.theirs and ctx.theirs != "HEAD^2" else None,
            "old_hash": plan.old_hash, "new_hash": plan.new_hash,
            "approvals": plan.approvals, "commits": plan.commits, "map": dict(mapping)})
    if ctx.merging:
        _git(root, "add", "-A", "--", *sorted(staged), ".plumb/log")
    core.store.invalidate()
    left = tuple(remaining) + _collision.collisions(core)
    return MergeFixResult(
        renumbered=tuple({"from": p.old, "to": p.new, "title": p.title, "kind": p.kind,
                          "references": p.references, "files": sorted(p.files),
                          "approvals": p.approvals, "commits": p.commits} for p in plans),
        remaining=left, staged=tuple(sorted(staged)) if ctx.merging else (),
        lines=tuple(_lines(plans, left, False)))


def _owner_plan(plans: Sequence[_Plan], path: str, mapping: Mapping[str, str],
                root: Path) -> _Plan:
    """The plan whose new ID the rewritten file now names (the first one, by default)."""
    try:
        text = (root / path).read_text(encoding="utf-8")
    except OSError:
        return plans[0]
    for plan in plans:
        if rewrite.token(plan.new).search(text):
            return plan
    return plans[0]
