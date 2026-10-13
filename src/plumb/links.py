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
    lone = link.kind == "verified_by" and link.example is not None and not others
    if lone and alive and core.status([record.id])[record.id].confirmation != "proposed":
        raise LinkError(f"{link_id} is the only test of {record.id} {link.example}, which the "
                        f"owner confirmed; removing it would leave that example without its "
                        f"test. Point it at the test's new place with plumb relink instead")
    kept = [other for other in record.links if other.index != link.index]
    core.store.set_links(record.id, [link_to_dict(other) for other in kept])
    renumbered = [{"from": other.id, "to": f"{record.id}#{n}"}
                  for n, other in enumerate(kept) if other.index != n]
    result = {"link": link_id, "kind": link.kind, "target": _describe(link.target),
              "example": link.example, "pin": _pin_dict(link.pin), "note": note,
              "renumbered": renumbered}
    core.log_append("events", "unlink", result)
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
                            f"{_describe(target)}; remove {link_id} with plumb unlink instead")
    moved = Link(source=record.id, index=link.index, kind=link.kind, target=target,
                 example=link.example, pin=Pin(source=record.hash, target=target_hash))
    raw = [link_to_dict(moved if other.index == link.index else other)
           for other in record.links]
    core.store.set_links(record.id, raw)
    result = {"link": link_id, "note": note,
              "old": {"target": _describe(link.target), "pin": _pin_dict(link.pin)},
              "new": {"target": _describe(target), "pin": _pin_dict(moved.pin)}}
    core.log_append("events", "relink", result)
    return result


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


REPIN_BUDGET_S = 120.0  # an explicit repin is not a hook: the turn budget would cut it short


def default_runner(core: Core) -> Callable[[list[str]], tuple[bool, str]]:
    """Run the covering tests of the changed paths through the verification lane."""

    def run(paths: list[str]) -> tuple[bool, str]:
        from plumb.verify import open_verify

        report = open_verify(core).run(changed=paths, budget_s=REPIN_BUDGET_S)
        if report.run_id is None:
            return False, "no test covers " + ", ".join(paths)
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
                      session: str | None = None, dry_run: bool = False) -> AfterTests:
    """Repin the stale links of ``selector`` (a link id or a record id) whose linked tests
    pass and whose change a model judges not to alter what the requirement relies on; refuse
    the others, with why. The judging is a cascade (SR-114): ``jev`` (the JEV tier, off
    without a threshold) clears a link alone, else ``judge`` (Sonnet) gives the verdict, and
    a link it says changed goes to ``diagnoser`` (Opus), whose finding is in ``diagnoses``: a
    card for the owner (filed in ``session``), a rewording, or the change sent back to
    development. ``dry_run`` asks the models only: no tests run, nothing is repinned, no card
    is filed, and the links it would repin are listed in ``would``. Never confirms anything."""
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
    from plumb.understand import repin as meaning_check

    if judge is None:
        judge = meaning_check.open_judge(core)
    if jev is None:
        jev = meaning_check.open_jev_tier(core)
    if judge is None and jev is None:
        result.refused += [(s.link.id, NO_MODEL) for s in candidates]
        return result
    if not dry_run:
        paths = sorted({p for p in (target_path(s.link.target) for s in candidates) if p})
        ok, detail = (runner or default_runner(core))(paths)
        if not ok:
            result.refused += [(s.link.id, f"its linked tests do not pass ({detail})")
                               for s in candidates]
            return result
    from plumb.understand.judge import record_text

    index = core.index()
    for state in candidates:
        link = state.link
        texts = end_texts(core.root, link)
        if texts is None:
            result.refused.append((link.id, "the earlier version of the end could not be "
                                   "found in git, so there is nothing to compare"))
            continue
        record = index.get(link.id.split("#")[0])
        path = target_path(link.target) or ""
        shown = dict(requirement=f"{record.id}: {record.title}\n{record_text(record)}"
                     if record is not None else link.id,
                     link_id=link.id, link_kind=link.kind, path=path,
                     before=texts[0], after=texts[1])
        p = jev.clears(**shown) if jev is not None else None
        if p is not None:   # EX-1: JEV alone, above its calibrated threshold
            why = f"JEV gives {p:.2f}, at or above its threshold {jev.threshold:.2f}"
            _repinned(core, result, link.id, "jev", why, dry_run)
            continue
        if judge is None:   # EX-6 leads to Sonnet; without it nothing is repinned on a guess
            result.refused.append((link.id, NO_MODEL))
            continue
        try:
            meaning = judge.same_meaning(**shown)
        except Exception as exc:  # noqa: BLE001 - an unreachable model refuses
            result.refused.append((link.id, f"{NO_MODEL} ({exc})"))
            continue
        if meaning.unchanged is None:
            result.refused.append((link.id, f"{NO_MODEL}: {meaning.reason}"))
        elif not meaning.unchanged:
            _diagnose(core, result, record, link, shown, meaning.reason, diagnoser,
                      session, dry_run)
        else:
            _repinned(core, result, link.id, "sonnet", meaning.reason, dry_run)
    return result


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
    from plumb.understand.judge import record_text

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
              dry_run: bool) -> None:
    """Sonnet says the change matters: Opus says which way it goes (SR-113, SR-114 EX-3..5).
    No diagnosis (no model, no usable answer) is the plain refusal: nothing is guessed."""
    from plumb.understand import repin as meaning_check

    refusal = CHANGED.format(reason=reason)
    if diagnoser is None:
        diagnoser = meaning_check.open_diagnoser(core)
    if diagnoser is None:
        result.refused.append((link.id, refusal))
        return
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
            "broken_example": found.broken_example, "turn": turn, "card": False,
            "consequences": list(found.consequences), "why": found.why}
    if found.outcome == "owner":
        from plumb import stale

        filed = dict(link=link.id, record=record_id, path=path, topic=topic,
                     issue=found.explanation, options=found.options,
                     consequences=found.consequences, why=found.why)
        missing = stale.card_missing(filed)
        if not dry_run:
            where = session or stale.current_session(core.root)
            stale.add_card(core.root, where, by="diagnosis",
                           turn=stale.turn_number(core.root, where), **filed)
            item["card"], item["session"] = True, where
        item["card_missing"] = missing
        action = f"brought to the owner as a card: {found.explanation}"
        if missing:   # SR-116: kept open, but not offered until the agent completes it
            action += ("; the card is not offered until it is complete, it lacks: "
                       + "; ".join(missing) + f" (plumb stale card {link.id} --consequences "
                       "\"...\" --why \"...\")")
    elif found.outcome == "reword":
        action = (f"{record_id} disagrees with its intent ({found.explanation}); reword it "
                  f"through plumb capture to: {found.proposed_wording}")
    else:
        asked = f"the turn \"{_clip(turn['text'])}\" ({turn['at']})" if turn else \
            "an unknown turn"
        action = (f"send it back to development: {asked} made a change "
                  f"({_diff_summary(shown['before'], shown['after'], path)}) that breaks "
                  f"{found.broken_example or 'an example of ' + record_id}; "
                  f"{found.explanation}")
    result.diagnoses.append(item)
    result.refused.append((link.id, f"{refusal}; {action}"))


def _clip(text: str, width: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


__all__ = ["ALLOWED", "AfterTests", "LinkError", "LinkUsageError", "add_link", "hash_target",
           "kind_allowed", "kind_problem", "link_states", "parse_cli_target",
           "records_for_paths", "repin", "repin_after_tests"]
