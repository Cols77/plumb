"""Hash-pinned links and staleness (spec 5.5).

A link lives in its source record's ``links`` list and pins the hash of both ends. Either end
moving makes it stale; a missing target makes it dangling; a link without a pin is unpinned.
Repinning refreshes pins, logs a ``repin`` event and never confirms anything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from plumb.contracts import Link, LinkState, Pin, Record, Target
from plumb.hashing import clean_rel_path, hash_target
from plumb.model import ID_PATTERN, kind_of, link_to_dict

if TYPE_CHECKING:
    from plumb.api import Core

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
    from plumb.hashing import split_test_node, symbol_qualname

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


def link_states(core: Core, ids: Iterable[str] | None = None) -> list[LinkState]:
    index = core.index()
    selected = index.keys() if ids is None else [i for i in ids if i in index]
    out: list[LinkState] = []
    for record_id in selected:
        record = index[record_id]
        for link in record.links:
            out.append(_state_of(link, record.hash, core.hash_target(link.target)))
    return out


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
    return link


def _describe(target: Target) -> str:
    if target.path and target.symbol and not target.test:
        from plumb.hashing import symbol_qualname

        return f"{target.path}::{symbol_qualname(target.symbol)}"
    return target.record or target.test or target.path or "?"


def repin(core: Core, selector: str | None = None, *, all_stale: bool = False,
          note: str = "") -> list[dict[str, Any]]:
    """Refresh pins of stale or unpinned links (or of one named link); logs one ``repin``."""
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
            if state.state == "current" or state.current is None:
                continue
            old = None if link.pin is None else {"from": link.pin.source, "to": link.pin.target}
            new = {"from": state.current.source, "to": state.current.target}
            new_links[link.index] = Link(source=link.source, index=link.index, kind=link.kind,
                                         target=link.target, example=link.example,
                                         pin=state.current)
            changes.append({"link": link.id, "old": old, "new": new})
            touched = True
        if touched:
            core.store.set_links(record_id, [link_to_dict(link) for link in new_links])
    if changes:
        core.log_append("events", "repin", {"links": changes, "note": note})
    return changes


def records_for_paths(core: Core, paths: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Each path mapped to the records it is a link end of, or whose record file it is."""
    from plumb.hashing import target_path

    ends: dict[str, set[str]] = {}
    for record in core.index().values():
        ends.setdefault(record.path, set()).add(record.id)
        for link in record.links:
            path = target_path(link.target)
            if path:
                rel = clean_rel_path(path)
                if rel:
                    ends.setdefault(rel, set()).add(record.id)
    out: dict[str, tuple[str, ...]] = {}
    for raw in paths:
        rel = clean_rel_path(raw) or raw
        out[raw] = tuple(sorted(ends.get(rel, ())))
    return out


__all__ = ["ALLOWED", "LinkError", "LinkUsageError", "add_link", "hash_target",
           "kind_allowed", "kind_problem", "link_states", "parse_cli_target",
           "records_for_paths", "repin"]
