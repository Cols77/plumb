"""Hash-pinned links and staleness (spec 5.5).

A link lives in its source record's ``links`` list and pins the hash of both ends. Either end
moving makes it stale; a missing target makes it dangling; a link without a pin is unpinned.
Repinning refreshes pins, logs a ``repin`` event and never confirms anything.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from plumb.contracts import Link, LinkState, Pin, Record, Target
from plumb.hashing import clean_rel_path, hash_target, target_path
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
# fallback, so a backend that is the heuristic, disabled or unreachable refuses.

REPIN_NOTE = "tests pass, meaning unchanged"
NO_MODEL = ("no model could judge whether the meaning changed (the judgment backend is "
            "unreachable or rule-based); nothing was repinned")
HISTORY_DEPTH = 30


@dataclass
class AfterTests:
    changes: list[dict[str, Any]] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)   # (link id, why)


def _segment(text: str, qualname: str | None) -> str | None:
    """The text of a whole file, or of one definition (as ``hashing`` cuts it)."""
    if not qualname:
        return text
    import ast
    import textwrap

    from plumb.hashing import _LINE_BREAK, find_definition

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


def end_texts(root: Path, link: Link) -> tuple[str, str] | None:
    """``(the end as the pin saw it, the end now)``: the pinned version is looked for among
    the file's committed versions (newest first); None when it is not found."""
    from plumb.hashing import split_test_node, symbol_qualname, target_path
    from plumb.normalize import sha256_text

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
    listing = _git_text(root, ["log", f"-n{HISTORY_DEPTH}", "--format=%H", "--", rel])
    for sha in (listing or "").split():
        text = _git_text(root, ["show", f"{sha}:{rel}"])
        before = None if text is None else _segment(text, qualname)
        if before is not None and sha256_text(before) == link.pin.target:
            return before, now or ""
    return None


def default_runner(core: Core) -> Callable[[list[str]], tuple[bool, str]]:
    """Run the covering tests of the changed paths through the verification lane."""

    def run(paths: list[str]) -> tuple[bool, str]:
        from plumb.verify import open_verify

        report = open_verify(core).run(changed=paths)
        if report.run_id is None:
            return False, "no test covers " + ", ".join(paths)
        return report.ok, ("passed" if report.ok else "failed: " + ", ".join(report.failed))

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
                      backend: Any = None) -> AfterTests:
    """Repin the stale links of ``selector`` (a link id or a record id) whose linked tests
    pass and whose end a model judges unchanged in meaning; refuse the others, with why.
    Never confirms anything."""
    result = AfterTests()
    states = _select_stale(core, selector)
    candidates: list[LinkState] = []
    for state in states:
        link = state.link
        if link.target.record is not None:
            result.refused.append((link.id, "it points at a record, not code: reword the "
                                   "record so it agrees, or bring it to the owner as a card"))
        elif state.moved != "target":
            result.refused.append((link.id, "the requirement itself was reworded since the "
                                   "pin: a test run cannot settle that; bring it to the owner "
                                   "as a card"))
        else:
            candidates.append(state)
    if not candidates:
        return result
    if backend is None:
        from plumb.judgment import get_backend

        try:
            backend = get_backend(core, hook=False)
        except Exception:  # noqa: BLE001
            backend = None
    if backend is None or getattr(backend, "name", "") in ("heuristic", "disabled"):
        result.refused += [(s.link.id, NO_MODEL) for s in candidates]
        return result
    paths = sorted({p for p in (target_path(s.link.target) for s in candidates) if p})
    ok, detail = (runner or default_runner(core))(paths)
    if not ok:
        result.refused += [(s.link.id, f"its linked tests do not pass ({detail})")
                           for s in candidates]
        return result
    for state in candidates:
        link = state.link
        texts = end_texts(core.root, link)
        if texts is None:
            result.refused.append((link.id, "the earlier version of the end could not be "
                                   "found in git, so there is nothing to compare"))
            continue
        try:
            judgments = list(backend.drift_triage([state], {link.id: texts}))
        except Exception:  # noqa: BLE001 - an unreachable model refuses
            judgments = []
        verdict = judgments[0] if judgments else None
        if verdict is None or verdict.backend in ("heuristic", "disabled") \
                or verdict.tier != "accept" or verdict.verdict not in ("cosmetic", "material"):
            result.refused.append((link.id, NO_MODEL))
        elif verdict.verdict == "material":
            result.refused.append((link.id, "the model says the meaning changed"))
        else:
            result.changes += repin(core, link.id, note=REPIN_NOTE)
    return result


__all__ = ["ALLOWED", "AfterTests", "LinkError", "LinkUsageError", "add_link", "hash_target",
           "kind_allowed", "kind_problem", "link_states", "parse_cli_target",
           "records_for_paths", "repin", "repin_after_tests"]
