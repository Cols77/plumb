"""Hash-pinned links and staleness (spec 5.5).

A link lives in its source record's ``links`` list and pins the hash of both ends. Either end
moving makes it stale; a missing target makes it dangling; a link without a pin is unpinned.
Repinning refreshes pins, logs a ``repin`` event and never confirms anything.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from iaso.contracts import Link, LinkState, Pin, Record, Target
from iaso.hashing import clean_rel_path, hash_target, target_path
from iaso.model import ID_PATTERN, kind_of, link_to_dict

if TYPE_CHECKING:
    from iaso.api import Core

RECORD_KINDS = frozenset({"intent", "requirement", "decision", "feature", "nc"})

# kind -> (allowed source kinds, allowed target categories); "same" = same kind as source
ALLOWED: Mapping[str, tuple[frozenset[str], frozenset[str]]] = {
    "derives_from": (frozenset({"requirement", "decision", "feature"}), frozenset({"intent"})),
    "decides": (frozenset({"decision"}), frozenset({"intent", "requirement"})),
    "upstream": (frozenset({"requirement"}), frozenset({"requirement"})),
    # relates_to a path: a document the requirement relates to, such as an imported
    # spec:<id> relation's spec (next-plan 9.1)
    "relates_to": (frozenset({"requirement"}), frozenset({"requirement", "code"})),
    "implemented_by": (frozenset({"requirement"}), frozenset({"code"})),
    "verified_by": (frozenset({"requirement"}), frozenset({"test", "code"})),
    "corrects": (frozenset({"nc"}), frozenset({"requirement", "code"})),
    "supersedes": (RECORD_KINDS, frozenset({"same"})),
}


class LinkError(ValueError):
    """A link that cannot be added or repinned (exit 1)."""


class LinkUsageError(LinkError):
    """A link target written in a form this build does not accept (exit 2)."""


def kind_allowed(kind: str, source_kind: str, target_category: str) -> bool:
    rule = ALLOWED.get(kind)
    if rule is None:
        return False
    sources, targets = rule
    if source_kind not in sources:
        return False
    if "same" in targets:
        return target_category == source_kind
    return target_category in targets


def target_category(target: Target) -> str | None:
    """The record kind of a record target, ``code`` for a path, ``test`` for a test node."""
    if target.record is not None:
        return kind_of(target.record)
    if target.test is not None:
        return "test"
    if target.path is not None:
        return "code"
    return None


def kind_problem(link: Link, source: Record) -> str | None:
    """Why a link's kind is not allowed between its ends, or None."""
    if link.kind not in ALLOWED:
        return f"{link.id}: unknown link kind {link.kind!r}"
    category = target_category(link.target)
    if category is None:
        return f"{link.id}: link has no target (to, path or test)"
    if not kind_allowed(link.kind, source.kind, category):
        return f"{link.id}: {link.kind} is not allowed from {source.kind} to {category}"
    if link.example is not None and link.kind != "verified_by":
        return f"{link.id}: only verified_by links name an example"
    return None


def parse_cli_target(text: str) -> Target:
    """``ID``, a repository-relative ``path``, or ``path::Qual.name`` (a symbol end; a
    ``verified_by`` link turns it into the test node ``path::name``, see ``end_for``)."""
    text = text.strip()
    if ID_PATTERN.match(text):
        return Target(record=text)
    raw_path, sep, name = text.partition("::")
    rel = clean_rel_path(raw_path)
    if rel is None:
        raise LinkUsageError(f"'{text}': a link end must be a repository-relative path")
    if not sep:
        return Target(path=rel)
    qualname = ".".join(p.strip() for p in name.split("::"))
    if not qualname or any(not p for p in qualname.split(".")):
        raise LinkUsageError(f"'{text}': name a definition after '::' (path::Qual.name)")
    return Target(path=rel, symbol=qualname)


def end_for(kind: str, target: Target) -> Target:
    """The stored form of a link end: a ``verified_by`` symbol end is a test node
    (``path::Class::name``, parametrize ids dropped); every other end is unchanged."""
    if kind != "verified_by" or not target.symbol or target.test or not target.path:
        return target
    from iaso.hashing import split_test_node, symbol_qualname

    node = f"{target.path}::" + "::".join(symbol_qualname(target.symbol).split("."))
    path, qualname = split_test_node(node)
    return Target(test=f"{path}::" + "::".join(qualname.split(".")))


def _state_of(link: Link, source_hash: str, target_hash: str | None) -> LinkState:
    if target_hash is None:
        return LinkState(link=link, state="dangling")
    current = Pin(source=source_hash, target=target_hash)
    if link.pin is None:
        return LinkState(link=link, state="unpinned", current=current)
    moved_source = link.pin.source != source_hash
    moved_target = link.pin.target != target_hash
    if not moved_source and not moved_target:
        return LinkState(link=link, state="current", current=current)
    moved = "both" if moved_source and moved_target else ("source" if moved_source else "target")
    return LinkState(link=link, state="stale", moved=moved, current=current)  # type: ignore[arg-type]


def link_states(core: Core, ids: Iterable[str] | None = None,
                only: Collection[str] | None = None) -> list[LinkState]:
    """The state of each link of ``ids`` (else of every record); ``only``: just these link
    ids, so a hook hashes no other end."""
    index = core.index()
    selected = index.keys() if ids is None else [i for i in ids if i in index]
    from iaso.frozen import is_frozen
    from iaso.query import retired_ids

    retired = retired_ids(index)
    out: list[LinkState] = []
    for record_id in selected:
        record = index[record_id]
        for link in record.links:
            if only is not None and link.id not in only:
                continue
            if record_id in retired:  # SR-164: a superseded record's pins are not tracked
                out.append(LinkState(link=link, state="retired"))
                continue
            if link.kind == "supersedes" and link.target.record not in index:
                out.append(LinkState(link=link, state="retired"))  # DEC-145: it went, per P15
                continue
            if is_frozen(core.config, link.target.path or link.target.test):
                out.append(LinkState(link=link, state="retired"))    # SR-380: a frozen part
                continue
            out.append(_state_of(link, record.hash, core.hash_target(link.target)))
    return out


def live_examples(core: Core, old_id: str, new_id: str = "") -> list[tuple[str, str]]:
    """Examples of ``old_id`` that a test still verifies and ``new_id`` does not already
    verify: ``[(EX-n, test)]``, one per link (SR-164)."""
    index = core.index()

    def tests(rid: str) -> list[tuple[str | None, str]]:
        record = index.get(rid)
        return [] if record is None else [
            (link.example, link.target.test or link.target.path or "")
            for link in record.links if link.kind == "verified_by"
            and (link.target.test or link.target.path)]

    kept = {t for _, t in tests(new_id)}
    return [(ex, t) for ex, t in tests(old_id) if ex and t not in kept]


def add_link(core: Core, source: str, kind: str, target: Target,
             example: str | None = None) -> Link:
    """Add a link with fresh pins on both ends; an identical existing link is returned."""
    target = end_for(kind, target)
    index = core.index()
    record = index.get(source)
    if record is None:
        raise LinkError(f"no record {source}")
    probe = Link(source=source, index=len(record.links), kind=kind, target=target,  # type: ignore[arg-type]
                 example=example)
    problem = kind_problem(probe, record)
    if problem:
        raise LinkError(problem)
    if example is not None and example not in {e.id for e in record.examples}:
        raise LinkError(f"{source} has no example {example}")
    target_hash = core.hash_target(target)
    if target_hash is None:
        raise LinkError(f"link end does not exist: {_describe(target)}")
    for existing in record.links:
        if (existing.kind, existing.target, existing.example) == (kind, target, example):
            return existing
    link = Link(source=source, index=len(record.links), kind=kind, target=target,  # type: ignore[arg-type]
                example=example, pin=Pin(source=record.hash, target=target_hash))
    raw = [link_to_dict(existing) for existing in record.links] + [link_to_dict(link)]
    core.store.set_links(source, raw)
    _keep_pinned_version(core, target, target_hash)
    return link


def _blob_store(root: Path) -> Path | None:
    common = _git_text(root, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    return Path(common.strip()) / "iaso" / "pin_blobs.json" if common else None


def _keep_pinned_version(core: Core, target: Target, target_hash: str) -> None:
    """SR-166 EX-2: a pin on an uncommitted file version keeps that version as a git blob,
    so the pinned text can be found after the file is committed again. Never fails the pin."""
    import json
    import os

    try:
        rel = clean_rel_path(target_path(target) or "")
        store = _blob_store(core.root)
        if rel is None or store is None or not _git_text(core.root,
                                                        ["status", "--porcelain", "--", rel]):
            return
        blob = (_git_text(core.root, ["hash-object", "-w", "--", rel]) or "").strip()
        if not blob:
            return
        try:
            known = json.loads(store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            known = {}
        known[target_hash] = blob
        store.parent.mkdir(parents=True, exist_ok=True)
        tmp = store.with_name(f"{store.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(known), encoding="utf-8")
        os.replace(tmp, store)
    except Exception:  # noqa: BLE001
        pass


def _describe(target: Target) -> str:
    if target.path and target.symbol and not target.test:
        from iaso.hashing import symbol_qualname

        return f"{target.path}::{symbol_qualname(target.symbol)}"
    return target.record or target.test or target.path or "?"


def repin(core: Core, selector: str | None = None, *, all_stale: bool = False,
          note: str = "", dry_run: bool = False) -> list[dict[str, Any]]:
    """Refresh pins of stale or unpinned links (or of one named link); logs one ``repin``.
    ``dry_run`` returns the changes it would make and writes nothing: no record file, no
    pinned-version blob, no log entry, no withdrawn card."""
    index = core.index()
    wanted: dict[str, set[int] | None] = {}
    if selector is not None:
        if "#" in selector:
            record_id, _, position = selector.partition("#")
            record = index.get(record_id)
            if record is None or not position.isdigit() or int(position) >= len(record.links):
                raise LinkError(f"no link {selector}")
            wanted[record_id] = {int(position)}
        else:
            if selector not in index:
                raise LinkError(f"no record {selector}")
            wanted[selector] = None
    elif all_stale:
        wanted = dict.fromkeys(index)
    else:
        raise LinkError("name a link id, a record id, or --all-stale")

    changes: list[dict[str, Any]] = []
    for record_id, positions in wanted.items():
        record = index[record_id]
        states = link_states(core, [record_id])
        new_links = list(record.links)
        touched = False
        for state in states:
            link = state.link
            explicit = positions is not None and link.index in positions
            if positions is not None and not explicit:
                continue
            if state.state == "dangling":
                if explicit:
                    raise LinkError(f"{link.id} is dangling: its target does not exist")
                continue
            if state.state in ("current", "retired") or state.current is None:
                continue
            old = None if link.pin is None else {"from": link.pin.source, "to": link.pin.target}
            new = {"from": state.current.source, "to": state.current.target}
            new_links[link.index] = Link(source=link.source, index=link.index, kind=link.kind,
                                         target=link.target, example=link.example,
                                         pin=state.current)
            changes.append({"link": link.id, "old": old, "new": new})
            if not dry_run:
                _keep_pinned_version(core, link.target, state.current.target)
            touched = True
        if touched and not dry_run:
            core.store.set_links(record_id, [link_to_dict(link) for link in new_links])
    if changes and not dry_run:
        core.log_append("events", "repin", {"links": changes, "note": note})
        _withdraw_settled_questions(core)
    return changes


def _withdraw_settled_questions(core: Core) -> None:
    """SR-161: the owner question about a link just settled is withdrawn in every session
    folder (SR-300 EX-3)."""
    from iaso.understand import judge

    judge.drop_settled_questions(core, {s.link.id for s in core.link_states()
                                             if s.state == "stale"})


def _named_link(core: Core, link_id: str) -> tuple[Record, Link]:
    record_id, _, position = link_id.partition("#")
    record = core.index().get(record_id)
    if record is None or not position.isdigit() or int(position) >= len(record.links):
        raise LinkError(f"no link {link_id}")
    return record, record.links[int(position)]


def _pin_dict(pin: Pin | None) -> dict[str, str] | None:
    return None if pin is None else {"from": pin.source, "to": pin.target}


def unlink(core: Core, link_id: str, note: str) -> dict[str, Any]:
    """Remove one link; the links after it move down by one (DEC-048). The only live test of
    an example the owner confirmed is refused (DEC-049); a dangling one may always go."""
    record, link = _named_link(core, link_id)
    alive = core.hash_target(link.target) is not None
    others = [other for other in record.links if other.index != link.index
              and other.kind == "verified_by" and other.example == link.example
              and core.hash_target(other.target) is not None]
    # a retired example (one the record no longer has, or one of a superseded record: DEC-065)
    # is no one's confirmed example
    from iaso.query import retired_ids

    lone = link.kind == "verified_by" and not others \
        and link.example in {example.id for example in record.examples} \
        and record.id not in retired_ids(core.index())
    if lone and alive and core.status([record.id])[record.id].confirmation != "proposed":
        raise LinkError(f"{link_id} is the only test of {record.id} {link.example}, which the "
                        f"owner confirmed; removing it would leave that example without its "
                        f"test. Point it at the test's new place with iaso relink instead")
    kept = [other for other in record.links if other.index != link.index]
    core.store.set_links(record.id, [link_to_dict(other) for other in kept])
    renumbered = [{"from": other.id, "to": f"{record.id}#{n}"}
                  for n, other in enumerate(kept) if other.index != n]
    result = {"link": link_id, "kind": link.kind, "target": _describe(link.target),
              "example": link.example, "pin": _pin_dict(link.pin), "note": note,
              "renumbered": renumbered}
    core.log_append("events", "unlink", result)
    _withdraw_settled_questions(core)
    return {**result, "untested": link.example if lone else None}


def relink(core: Core, link_id: str, target: Target, note: str) -> dict[str, Any]:
    """Point one link at a new target, keeping its number, kind and example, with fresh pins
    on both ends."""
    record, link = _named_link(core, link_id)
    target = end_for(link.kind, target)
    moved = Link(source=record.id, index=link.index, kind=link.kind, target=target,
                 example=link.example)
    problem = kind_problem(moved, record)
    if problem:
        raise LinkError(problem)
    target_hash = core.hash_target(target)
    if target_hash is None:
        raise LinkError(f"link end does not exist: {_describe(target)}")
    for other in record.links:
        if other.index != link.index and \
                (other.kind, other.target, other.example) == (link.kind, target, link.example):
            raise LinkError(f"{other.id} already links {record.id} {link.kind} "
                            f"{_describe(target)}; remove {link_id} with iaso unlink instead")
    moved = Link(source=record.id, index=link.index, kind=link.kind, target=target,
                 example=link.example, pin=Pin(source=record.hash, target=target_hash))
    raw = [link_to_dict(moved if other.index == link.index else other)
           for other in record.links]
    core.store.set_links(record.id, raw)
    _keep_pinned_version(core, target, target_hash)
    result = {"link": link_id, "note": note,
              "old": {"target": _describe(link.target), "pin": _pin_dict(link.pin)},
              "new": {"target": _describe(target), "pin": _pin_dict(moved.pin)}}
    core.log_append("events", "relink", result)
    _withdraw_settled_questions(core)
    return result


def records_for_paths(core: Core, paths: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Each path mapped to the records it is a link end of, or whose record file it is."""
    from iaso.hashing import target_path

    index = core.index()
    memo = getattr(core, "_ends_memo", None)  # kept while the record index is the same one
    if memo is not None and memo[0] is index:
        ends = memo[1]
    else:
        ends = {}
        for record in index.values():
            ends.setdefault(record.path, set()).add(record.id)
            for link in record.links:
                path = target_path(link.target)
                if path:
                    rel = clean_rel_path(path)
                    if rel:
                        ends.setdefault(rel, set()).add(record.id)
        try:
            core._ends_memo = (index, ends)
        except AttributeError:
            pass
    out: dict[str, tuple[str, ...]] = {}
    for raw in paths:
        rel = clean_rel_path(raw) or raw
        out[raw] = tuple(sorted(ends.get(rel, ())))
    return out


# --------------------------------------------------------------------------- repin after tests
# SR-111 EX-4: a stale link whose tests pass and whose end a model judges unchanged in meaning
# is repinned without the owner. The reading is the model's alone (INT-029): no rule-based
# fallback, so a backend that is disabled or unreachable refuses. SR-114: JEV is asked first
# and repins alone above its calibrated threshold; Sonnet judges the rest; a link Sonnet says
# changed goes to Opus, which says whether the record is reworded, the change goes back to
# development, or the owner gets a card (SR-113).

REPIN_NOTE = "tests pass, meaning unchanged"
NO_MODEL = "no model could judge whether the meaning changed; nothing was repinned"
CHANGED = "the model says the meaning changed: {reason}"
HISTORY_DEPTH = 30


@dataclass
class AfterTests:
    changes: list[dict[str, Any]] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)   # (link id, why)
    would: list[tuple[str, str]] = field(default_factory=list)     # dry run: (link id, why)
    # SR-114: what Opus found for each link Sonnet says changed (see ``_diagnosis_item``)
    diagnoses: list[dict[str, Any]] = field(default_factory=list)
    unreachable: str = ""   # SR-174: why no model could judge (the check waits, nothing decided)


def _segment(text: str, qualname: str | None) -> str | None:
    """The text of a whole file, or of one definition (as ``hashing`` cuts it)."""
    if not qualname:
        return text
    import ast
    import textwrap

    from iaso.hashing import _LINE_BREAK, find_definition

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    node = find_definition(tree, qualname)
    if node is None or getattr(node, "end_lineno", None) is None:
        return None
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return textwrap.dedent("\n".join(_LINE_BREAK.split(text)[start - 1:node.end_lineno]))


def _git_text(root: Path, args: list[str]) -> str | None:
    import subprocess

    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=10,
                                check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _log_versions(root: Path, rev: str, flags: list[str], rel: str) -> list[tuple[str, str]]:
    """One ``git log`` listing of ``rel``: ``(commit, path)`` of each distinct content, newest
    first, at most ``HISTORY_DEPTH`` of them. A branch that merges main often has hundreds of
    merge commits carrying one version; counting commits (``-n``) ran out before the pinned
    version, so contents are counted (report-a425a319)."""
    listing = _git_text(root, ["log", *flags, "--format=@%H", "--raw", "--no-abbrev", rev, "--",
                               rel]) or ""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    sha = None
    for line in listing.splitlines():
        if line.startswith("@"):
            sha = line[1:]
        elif line.startswith(":") and sha:
            meta, *paths = line.split("\t")
            blob = meta.split()[3]
            if blob not in seen and set(blob) != {"0"}:   # a deletion has no content
                seen.add(blob)
                found.append((sha, paths[-1]))
                if len(found) >= HISTORY_DEPTH:
                    break
    return found


def _versions(root: Path, rel: str) -> list[tuple[str, str]]:
    """``(commit, path)`` of ``rel``'s last versions, newest first: HEAD's, then, during a merge,
    the incoming side's, whose history HEAD does not reach until the merge is recorded. The path
    is the file's at that commit: a renamed file (the IASO rename moved every one) is followed."""
    revs = ["HEAD"] + (["MERGE_HEAD"] if _git_text(root, ["rev-parse", "-q", "--verify",
                                                         "MERGE_HEAD"]) else [])
    found: list[tuple[str, str]] = []
    for rev in revs:
        # --full-history: a merge that kept one side's file hides the other side's versions;
        # --diff-merges: a merge names its files too, so a version only a merge made is found
        # (report-645da35a). --follow alone loses a merge that renamed and changed the file
        # (the IASO rename merged into a branch), so the plain path is listed too.
        flags = ["--full-history", "--diff-merges=first-parent"]
        listings = [_log_versions(root, rev, ["--follow", *flags], rel),
                    _log_versions(root, rev, flags, rel)]
        from iaso.convert import restore_old

        # --follow misses a small file whose conversion to IASO changed too much of it (SR-432)
        before = restore_old(rel)
        if before != rel:
            listings.append(_log_versions(root, rev, flags, before))
        found += [v for listing in listings for v in listing if v not in found]
    return found


def _texts_at(root: Path, sha: str, at: str, rel: str) -> list[str]:
    """The file as committed at ``sha`` under its path then, ``at``. A version from before the
    conversion to IASO (SR-432, a different path) is also read as the converter rewrote it: a pin
    made before the rename hashes the first, a pin the converter carried over the second. At the
    rename commit itself ``git log --follow`` names the old path while the file is already at the
    new one, so the current path and the old-name path are tried too."""
    from iaso.convert import restore_old, rewrite_text

    for path in dict.fromkeys((at, rel, restore_old(rel))):
        text = _git_text(root, ["show", f"{sha}:{path}"])
        if text is not None:
            return [text] if path == rel else [text, rewrite_text(text)]
    return []


def end_texts(root: Path, link: Link) -> tuple[str, str] | None:
    """``(the end as the pin saw it, the end now)``: the pinned version is looked for among
    the file's committed versions (newest first); None when it is not found."""
    from iaso.hashing import split_test_node, symbol_qualname, target_path
    from iaso.normalize import sha256_text

    target = link.target
    path = target_path(target)
    rel = clean_rel_path(path) if path else None
    if rel is None or link.pin is None:
        return None
    qualname = None
    if target.test:
        qualname = split_test_node(target.test)[1]
    elif target.symbol:
        qualname = symbol_qualname(target.symbol)
    try:
        now = _segment((Path(root) / rel).read_text(encoding="utf-8"), qualname)
    except (OSError, UnicodeDecodeError):
        return None
    for sha, at in _versions(root, rel):
        for text in _texts_at(root, sha, at, rel):
            before = _segment(text, qualname)
            if before is not None and sha256_text(before) == link.pin.target:
                return before, now or ""
    # shortcut: a loose blob can be pruned by git gc after ~2 weeks; record the pin in a ref if repins come later than that
    store = _blob_store(root)
    try:
        import json
        blob = json.loads(store.read_text(encoding="utf-8")).get(link.pin.target) if store else None
    except (OSError, ValueError):
        blob = None
    text = _git_text(root, ["cat-file", "blob", blob]) if blob else None
    before = None if text is None else _segment(text, qualname)
    if before is not None and sha256_text(before) == link.pin.target:
        return before, now or ""
    return None


REPIN_BUDGET_S = 120.0  # an explicit repin is not a hook: the turn budget would cut it short
# SR-310: inside a hook the stale check gets the hook's remaining time, never more; a link it
# cannot reach in time waits (SR-174), it is not refused and no case is opened
OUT_OF_TIME = "the stale check ran out of the hook's time"


def test_budget_s(core: Core, budget_s: float | None) -> float:
    """The test run's budget: ``REPIN_BUDGET_S``, or less so that the run's kill, which the
    lane sets at ``budget * verify.hard_limit_factor``, lands inside the ``budget_s`` left."""
    if budget_s is None:
        return REPIN_BUDGET_S
    factor = max(float(core.config.verify.hard_limit_factor), 1.0)
    return min(REPIN_BUDGET_S, max(float(budget_s), 0.0) / factor)


def _time_limit(model: Any, seconds: float | None) -> None:
    """Cut ``model``'s next call to ``seconds`` when it can be (``time_limit``, on the
    judges of ``understand.repin``); a stub without one is left alone."""
    limit = getattr(model, "time_limit", None)
    if seconds is not None and callable(limit):
        limit(max(float(seconds), 0.0))


def default_runner(core: Core,
                   budget_s: float | None = None) -> Callable[[list[str]], tuple[bool, str]]:
    """Run the covering tests of the changed paths through the verification lane, within
    ``budget_s`` (the caller's remaining time; ``REPIN_BUDGET_S`` for an explicit repin)."""

    def run(paths: list[str]) -> tuple[bool, str]:
        from iaso.verify import open_verify

        report = open_verify(core).run(changed=paths, budget_s=test_budget_s(core, budget_s))
        deferred = getattr(getattr(report, "selection", None), "deferred", ())
        if budget_s is not None and (report.timed_out if report.run_id is not None
                                     else bool(deferred)):
            # the hook's time ran out before the tests did: the check waits, nothing failed
            return False, OUT_OF_TIME
        if report.run_id is None:
            # SR-166: an untested end is judged on meaning alone; the judge below still gates
            return True, "no test covers " + ", ".join(paths) + ": judged on meaning only"
        if report.ok and report.flaky:   # SR-254 EX-22: a link rests on a clean first-attempt pass
            return False, "needed a retry to pass: " + ", ".join(report.flaky)
        if report.ok:
            return True, "passed"
        if report.failed:
            return False, "failed: " + ", ".join(report.failed)
        why = (["stopped at the time limit"] if report.timed_out else []) \
            + ([f"aborted: {report.aborted}"] if report.aborted else []) \
            + ([f"discarded: {report.discarded}"] if report.discarded else []) \
            + (["collection errors: " + ", ".join(report.collection_errors)]
               if report.collection_errors else [])
        return False, "; ".join(why) or "the run did not finish"

    return run


def _select_stale(core: Core, selector: str) -> list[LinkState]:
    index = core.index()
    if "#" in selector:
        record_id, _, position = selector.partition("#")
        record = index.get(record_id)
        if record is None or not position.isdigit() or int(position) >= len(record.links):
            raise LinkError(f"no link {selector}")
        return [s for s in core.link_states([record_id])
                if s.link.index == int(position) and s.state == "stale"]
    if selector not in index:
        raise LinkError(f"no record {selector}")
    return [s for s in core.link_states([selector]) if s.state == "stale"]


def repin_after_tests(core: Core, selector: str, *,
                      runner: Callable[[list[str]], tuple[bool, str]] | None = None,
                      judge: Any = None, jev: Any = None, diagnoser: Any = None,
                      session: str | None = None, dry_run: bool = False,
                      auto: bool = False, budget_s: float | None = None) -> AfterTests:
    """Repin the stale links of ``selector`` (a link id or a record id) whose linked tests
    pass and whose change a model judges not to alter what the requirement relies on; refuse
    the others, with why. The judging is a cascade (SR-114): ``jev`` (the JEV tier, off
    without a threshold) clears a link alone, else ``judge`` (Sonnet) gives the verdict, and
    a link it says changed goes to ``diagnoser`` (Opus), whose finding is in ``diagnoses``: a
    card for the owner (filed in ``session``), a rewording, or the change sent back to
    development. ``dry_run`` asks the models only: no tests run, nothing is repinned, no card
    is filed, and the links it would repin are listed in ``would``. ``auto`` (SR-175, the turn
    end): a rewording Opus proposes is recorded as an unconfirmed edit and the link repinned,
    where the command only tells the agent to reword. A link to a record (a decision's
    ``decides``) runs no tests: the record as pinned and as it is now go to the same cascade,
    and a changed meaning is one owner question through the question tool (SR-300 EX-3), not a
    diagnosis. ``budget_s`` (SR-310, a hook's remaining time): the test run is bounded by it,
    each model call is cut to the time left and none starts past it; the links not reached
    wait (``unreachable`` says why), as when no model answers. Never confirms anything."""
    result = AfterTests()
    states = _select_stale(core, selector)
    candidates = list(states)   # a reworded requirement is judged too (its old wording shown)
    if not candidates:
        return result
    end = None if budget_s is None else time.monotonic() + max(float(budget_s), 0.0)

    def left() -> float | None:
        return None if end is None else end - time.monotonic()

    def out_of_time(link_id: str) -> bool:
        if end is None or time.monotonic() < end:
            return False
        result.refused.append((link_id, OUT_OF_TIME))
        result.unreachable = OUT_OF_TIME
        return True

    if end is not None and time.monotonic() >= end:
        for s in candidates:
            out_of_time(s.link.id)
        return result
    from iaso.understand import repin as meaning_check

    if judge is None:
        judge = meaning_check.open_judge(core)
    if jev is None:
        jev = meaning_check.open_jev_tier(core)
    if judge is None and jev is None:   # issue #5: the case says why, not only that
        result.unreachable = meaning_check.judge_gap(core)
        result.refused += [(s.link.id, f"{NO_MODEL}: {result.unreachable}")
                           for s in candidates]
        return result
    untested = ""
    paths = sorted({p for p in (target_path(s.link.target) for s in candidates) if p})
    if not dry_run and paths:   # a link to a record (SR-300 EX-3) has no tests to run
        if runner is None:   # an explicit repin keeps the plain call
            runner = default_runner(core) if end is None else default_runner(core, left())
        ok, detail = runner(paths)
        if not ok and detail == OUT_OF_TIME:
            result.refused += [(s.link.id, OUT_OF_TIME)
                               for s in candidates if target_path(s.link.target)]
            result.unreachable = OUT_OF_TIME
            candidates = [s for s in candidates if not target_path(s.link.target)]
        elif not ok:
            result.refused += [(s.link.id, f"its linked tests do not pass ({detail})")
                               for s in candidates if target_path(s.link.target)]
            candidates = [s for s in candidates if not target_path(s.link.target)]
        elif detail.startswith("no test covers"):
            untested = f" (no test gate: {detail})"
    from iaso.understand.judge import record_text

    index = core.index()
    gap = ""
    for state in candidates:
        link = state.link
        if out_of_time(link.id):   # SR-310: a judge call past the deadline outlives the hook
            continue
        target = index.get(link.target.record or "")
        texts = (_record_texts(core.root, target, link) if link.target.record is not None
                 else end_texts(core.root, link))
        if texts is None:
            result.refused.append((link.id, "the earlier version of the end could not be "
                                   "found in git, so there is nothing to compare"))
            continue
        record = index.get(link.id.split("#")[0])
        path = target_path(link.target) or (target.path if target is not None else "")
        reworded = ""
        if state.moved != "target" and record is not None and link.pin is not None:
            reworded = _pinned_text(core.root, record, link.pin.source) or ""
            if not reworded:
                result.refused.append((link.id, "the requirement as pinned could not be found "
                                       "in git, so there is nothing to compare its wording to"))
                continue
        shown = dict(requirement=f"{record.id}: {record.title}\n{record_text(record)}"
                     if record is not None else link.id,
                     link_id=link.id, link_kind=link.kind, path=path,
                     before=texts[0], after=texts[1], requirement_before=reworded)
        newer = _later_decisions(index, link, target or record)
        if newer:   # SR-242, INT-079: the cascade still decides, reading the owner's later answers
            shown["requirement"] += (
                "\n\nThe owner decided later, on the record as it is now; a later answer "
                "supersedes the earlier one on the same point, so a change that applies it "
                "keeps the meaning:\n"
                + "\n".join(f"{d.id}: {record_text(d)}" for d in newer))
        _time_limit(jev, left())   # SR-310: no model call outlives the hook's time
        p = jev.clears(**shown) if jev is not None else None
        if p is not None:   # EX-1: JEV alone, above its calibrated threshold
            why = f"JEV gives {p:.2f}, at or above its threshold {jev.threshold:.2f}"
            _repinned(core, result, link.id, "jev", why + untested, dry_run)
            continue
        if judge is None:   # EX-6 leads to Sonnet; without it nothing is repinned on a guess
            gap = gap or meaning_check.judge_gap(core)
            result.refused.append((link.id, f"{NO_MODEL}: JEV gave it less than its threshold "
                                   f"and the meaning judge cannot run ({gap})"))
            continue
        if out_of_time(link.id):   # JEV used the time up: Sonnet does not start
            continue
        _time_limit(judge, left())
        try:
            meaning = judge.same_meaning(**shown)
        except Exception as exc:  # noqa: BLE001 - an unreachable model refuses
            result.refused.append((link.id, f"{NO_MODEL} ({exc})"))
            result.unreachable = str(exc)
            continue
        if meaning.unchanged is None:
            result.refused.append((link.id, f"{NO_MODEL}: {meaning.reason}"))
            if meaning.unreachable:
                result.unreachable = meaning.reason
        elif not meaning.unchanged and target is not None:   # SR-300 EX-3, SR-221
            _ask_owner(core, result, record, target, link, shown, meaning.reason, session,
                       dry_run)
        elif not meaning.unchanged and out_of_time(link.id):   # Opus would outlive the hook
            pass
        elif not meaning.unchanged:
            _diagnose(core, result, record, link, shown, meaning.reason, diagnoser,
                      session, dry_run, auto, budget_s=left())
        else:
            _repinned(core, result, link.id, "sonnet", meaning.reason + untested, dry_run)
    return result


def _later_decisions(index: Mapping[str, Record], link: Link,
                     about: Record | None) -> list[Record]:
    """The other decisions that decide ``about`` (the record end of a decision's link, or the
    requirement a code link serves) and are pinned to it as it is now: the owner decided again
    after this link's pin, so the judge reads the change next to those answers (a change that
    applies them keeps the meaning); the verdict stays the cascade's (SR-242)."""
    if about is None:
        return []
    return [record for record in index.values()
            if record.kind == "decision" and record.id != link.source
            and any(other.target.record == about.id and other.pin is not None
                    and other.pin.target == about.hash for other in record.links)]


def _pinned_text(root: Path, record: Record, pin_hash: str) -> str | None:
    """What ``record`` asserted at the version whose hash is ``pin_hash``, looked for among its
    file's committed versions (newest first); None when it is not found."""
    from iaso.model import parse_record
    from iaso.understand.judge import record_text

    for sha, at in _versions(root, record.path):
        for text in _texts_at(root, sha, at, record.path):
            try:
                old = parse_record(text, record.path)
            except Exception:  # noqa: BLE001 - a version that does not parse is not the pinned one
                continue
            if old.hash == pin_hash:
                return record_text(old)
    return None


def _record_texts(root: Path, target: Record | None, link: Link) -> tuple[str, str] | None:
    """``(the target record as the pin saw it, as it is now)``, each as what it asserts: the
    pinned version is looked for among the record file's committed versions (newest first);
    None when it is not found."""
    from iaso.understand.judge import record_text

    if target is None or link.pin is None:
        return None
    old = _pinned_text(root, target, link.pin.target)
    return None if old is None else (old, record_text(target))


def _owner_answer(core: Core, link: Link, target: Record, record: Record | None) -> str | None:
    """The owner's latest answer to this link's question asked at the versions now on file:
    a rerun reads the change in new words, and asking again would ask the same thing twice."""
    if record is None:
        return None
    now = {(target.id, target.hash), (record.id, record.hash)}
    for e in reversed(core.events()):
        asked = e.payload.get("asked") if e.kind == "question-answer" else None
        if isinstance(asked, Mapping) and asked.get("job") == f"debug:{link.id}" and {
                (r.get("id"), r.get("hash")) for r in asked.get("records") or ()
                if isinstance(r, Mapping)} == now:
            return str(e.payload.get("answer") or "")
    return None


def _ask_owner(core: Core, result: AfterTests, record: Record | None, target: Record,
               link: Link, shown: Mapping[str, str], reason: str, session: str | None,
               dry_run: bool) -> None:
    """SR-300 EX-3, SR-221: the record a decision settles changed in meaning: one question to
    the owner through the question tool, about the behaviour and in plain words; no card, no
    diagnosis. The link stays stale until the answer is applied."""
    from iaso import stale
    from iaso.understand import judge

    refusal = CHANGED.format(reason=reason)
    said_before = _owner_answer(core, link, target, record)
    if said_before is not None:     # SR-362 EX-2: the owner answered at these versions
        if said_before.startswith("It still holds"):
            _repinned(core, result, link.id, "owner", f'the owner answered "{said_before}"',
                      dry_run)
        else:
            result.refused.append((link.id, f'{refusal}; the owner answered "{said_before}"'))
        return
    if record is None or dry_run:
        result.refused.append((link.id, f"{refusal} (dry run: no question asked)" if dry_run
                               else refusal))
        return
    fields = record.fields
    chosen = str(fields.get("chosen") or record.title)
    asked = str(fields.get("question") or record.title)
    said = str(fields.get("rationale") or "").strip()
    came_from = "; ".join(i["text"].splitlines()[0] for i in _intents(core, record))
    dated = (_git_text(core.root, ["log", "--diff-filter=A", "--format=%cs", "--",
                                   record.path]) or "").split()
    # SR-267: one question, readable cold: the request it came from and its date, both
    # wordings side by side, the recommended option first with its reason, each option's
    # consequence and what it leaves undone; the owner's terms, no iaso vocabulary
    text = (f'"{target.title}" changed since you answered "{chosen}" to "{asked}". '
            f"Does your answer still hold for what it says now?\n\n"
            f"Then: {shown['before']}\n\nNow: {shown['after']}\n\n"
            f"What changed: {reason}\n\n"
            f'It comes from your decision "{asked}"'
            + (f" of {dated[-1]}" if dated else "")
            + (f' under your request "{came_from}"' if came_from else "")
            + (f" ({said})" if said else "") + ".")
    where = session or stale.current_session(core.root)
    judge.add_question(core, where, {
        "key": judge.question_key(text), "job": f"debug:{link.id}",
        "records": [{"id": target.id, "hash": target.hash},
                    {"id": record.id, "hash": record.hash}],
        "question": text, "header": "Decision",
        "options": [{"label": "It needs a new answer (Recommended)",
                     "description": f'Does: you are asked again what to decide, and "'
                                    f'{target.title}" keeps its new wording. Leaves undone: '
                                    "your old answer is not applied to the new wording. "
                                    "Recommended: the change reads as one your answer did not "
                                    "cover."},
                    {"label": "It still holds",
                     "description": "Does: your answer is kept and tied to the new wording. "
                                    "Leaves undone: nothing is asked again and the reading "
                                    "above is set aside."},
                    {"label": "Undo the new wording",
                     "description": f'Does: "{target.title}" goes back to what it said when you '
                                    "answered. Leaves undone: the work that changed it is not "
                                    "applied."}]})
    result.refused.append((link.id, f"{refusal}; one question to the owner through the "
                           f"question tool; on \"it still holds\", iaso repin {link.id}"))


def _repinned(core: Core, result: AfterTests, link_id: str, tier: str, why: str,
              dry_run: bool) -> None:
    """Repin ``link_id`` with a note naming the tier that cleared it (or list it, dry)."""
    if dry_run:
        result.would.append((link_id, f"{tier}: {why}"))
        return
    changes = repin(core, link_id, note=f"{REPIN_NOTE} ({tier}): {why}")
    for change in changes:
        change["tier"] = tier
    result.changes += changes


def _intents(core: Core, record: Record | None) -> list[dict[str, str]]:
    from iaso.understand.judge import record_text

    if record is None:
        return []
    index = core.index()
    out = []
    for link in record.links:
        target = index.get(link.target.record or "")
        if link.kind == "derives_from" and target is not None:
            out.append({"id": target.id, "text": f"{target.title}\n{record_text(target)}"})
    return out


def _diff_summary(before: str, after: str, path: str) -> str:
    import difflib

    added = removed = 0
    old, new = before.splitlines(), after.splitlines()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new).get_opcodes():
        if op != "equal":
            removed += i2 - i1
            added += j2 - j1
    return f"{path}: +{added}/-{removed} lines"


def _diagnose(core: Core, result: AfterTests, record: Record | None, link: Link,
              shown: Mapping[str, str], reason: str, diagnoser: Any, session: str | None,
              dry_run: bool, auto: bool = False, budget_s: float | None = None) -> None:
    """Sonnet says the change matters: Opus says which way it goes (SR-113, SR-114 EX-3..5).
    No diagnosis (no model, no usable answer) is the plain refusal: nothing is guessed.
    ``budget_s`` (SR-310): the time left to the hook; Opus's call is cut to it."""
    from iaso.understand import repin as meaning_check

    refusal = CHANGED.format(reason=reason)
    if diagnoser is None:
        diagnoser = meaning_check.open_diagnoser(core)
    if diagnoser is None:
        result.refused.append((link.id, refusal))
        return
    _time_limit(diagnoser, budget_s)
    path = shown["path"]
    change = meaning_check.diff(shown["before"], shown["after"], path)
    turn = meaning_check.turn_before(core, path)
    try:
        found, why = diagnoser.diagnose(
            requirement=shown["requirement"], intents=_intents(core, record), link_id=link.id,
            path=path, change=change, reason=reason, turn=turn)
    except Exception as exc:  # noqa: BLE001 - an unreachable model diagnoses nothing
        found, why = None, str(exc)
    if found is None:
        result.refused.append((link.id, f"{refusal} (no diagnosis: {why})"))
        return
    record_id = record.id if record is not None else link.source
    topic = found.topic or (record.title if record is not None else record_id)
    item = {"link": link.id, "record": record_id, "path": path, "outcome": found.outcome,
            "topic": topic, "explanation": found.explanation,
            "proposed_wording": found.proposed_wording, "options": list(found.options),
            "broken_example": found.broken_example, "turn": turn, "asked": False,
            "consequences": list(found.consequences), "why": found.why, "other": found.other}
    asks = found.outcome == "owner"
    if found.outcome == "contradicts":   # SR-175 EX-3: only two confirmed records contradict
        known = core.status([record_id, found.other]) if found.other in core.index() else {}
        asks = len(known) == 2 and all(s.confirmation == "confirmed" for s in known.values())
        item["other"] = found.other
    if asks:
        from iaso import stale

        if not dry_run:
            where = session or stale.current_session(core.root)
            item["asked"] = stale.ask_owner(
                core, where, link=link.id, record=record_id, topic=topic,
                issue=found.explanation, options=found.options,
                consequences=found.consequences, why=found.why,
                by="contradiction" if found.outcome == "contradicts" else "diagnosis")
            item["session"] = where
        action = ("filed as a question for the owner, to ask with the question tool: "
                  f"{found.explanation}")
        if not dry_run and not item["asked"]:
            action = (f"needs the owner but lacks a topic, an issue or two options to ask: "
                      f"{found.explanation}")
    elif found.outcome == "reword" and auto and not dry_run and (changes := reword_and_repin(
            core, record, link, found.proposed_wording,
            f"{REPIN_NOTE} (reworded, unconfirmed edit): {found.explanation}")) is not None:
        result.changes += changes
        return
    elif found.outcome == "reword":
        action = (f"{record_id} disagrees with its intent ({found.explanation}); reword it "
                  f"through iaso capture to: {found.proposed_wording}")
    elif found.outcome == "contradicts":   # not two confirmed records: nothing to ask which wins
        action = (f"{record_id} may disagree with {found.other}, but both are not confirmed, so "
                  f"no question asks which wins: {found.explanation}")
    else:
        asked = f"the turn \"{_clip(turn['text'])}\" ({turn['at']})" if turn else \
            "an unknown turn"
        action = (f"send it back to development: {asked} made a change "
                  f"({_diff_summary(shown['before'], shown['after'], path)}) that breaks "
                  f"{found.broken_example or 'an example of ' + record_id}; "
                  f"{found.explanation}")
    result.diagnoses.append(item)
    result.refused.append((link.id, f"{refusal}; {action}"))


def reword_and_repin(core: Core, record: Record | None, link: Link, wording: str,
                     note: str) -> list[dict[str, Any]] | None:
    """SR-175 EX-4, SR-172: record ``wording`` as the record's statement (a confirmed record
    reworded is an unconfirmed edit) and repin the link; the repin changes, or None when
    there is no statement to reword."""
    if record is None or not wording or "statement" not in record.fields:
        return None
    from iaso.capture.records import rewrite

    rewrite(core, record, {"statement": wording})
    return repin(core, link.id, note=note)


def restore_pins(core: Core, changes: Iterable[Mapping[str, Any]]) -> None:
    """Put back the pins a repin changed (``repin`` returns them: ``old`` is the pin before)."""
    for change in changes:
        record, link = _named_link(core, str(change["link"]))
        old = change.get("old")
        pin = Pin(old["from"], old["to"]) if old else None
        core.store.set_links(record.id, [
            link_to_dict(Link(source=o.source, index=o.index, kind=o.kind, target=o.target,
                              example=o.example, pin=pin if o.index == link.index else o.pin))
            for o in record.links])


def _clip(text: str, width: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


__all__ = ["ALLOWED", "AfterTests", "LinkError", "LinkUsageError", "add_link", "hash_target",
           "kind_allowed", "kind_problem", "link_states", "parse_cli_target",
           "records_for_paths", "repin", "repin_after_tests"]
