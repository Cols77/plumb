"""Ownership proposals for untraced changes, "does this diff serve its claimed SRs?", and
proposed test nodes (R12.3; sp2 10.1, SR-044).

All of them are proposals for the agent's read-back or one-line warnings: none writes a link,
none blocks a commit, and the claims result is the same with and without judgments.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from plumb.contracts import Proposal

if TYPE_CHECKING:
    from plumb.api import Core

MAX_CANDIDATES = 5
WARN_CONFIDENCE = 0.8


def _ends(record: Any) -> list[str]:
    from plumb.hashing import target_path

    out = []
    for link in record.links:
        if link.kind in ("implemented_by", "verified_by"):
            path = target_path(link.target)
            if path:
                out.append(path)
    return out


def candidates(core: Core, path: str) -> list[str]:
    """Requirements whose ends share the package of ``path`` or its direct imports, at most
    ``MAX_CANDIDATES``, nearest first."""
    index = core.index()
    package = str(PurePosixPath(path).parent)
    imported: set[str] = set()
    if path.endswith(".py"):
        try:
            from plumb.verify.imports import direct_imports

            imported = direct_imports(core.root, path, core.config.source_dirs)
        except Exception:  # noqa: BLE001 - the import map is optional here
            imported = set()
    scored: list[tuple[int, str]] = []
    for record in index.values():
        if record.kind != "requirement":
            continue
        ends = _ends(record)
        rank = 0
        if any(e in imported for e in ends):
            rank = 2
        elif any(str(PurePosixPath(e).parent) == package for e in ends):
            rank = 1
        if rank:
            scored.append((rank, record.id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [record_id for _, record_id in scored[:MAX_CANDIDATES]]


def _context(core: Core, path: str) -> str:
    try:
        text = (core.root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    return f"{path}\n{text[:4000]}"


def ownership_proposals(core: Core, paths: Sequence[str], *,
                        backend: Any = None) -> dict[str, Proposal]:
    """For each untraced path of ``paths``: the proposed owning requirement, chosen by the
    backend among the candidates (a Choice plus "none")."""
    from plumb.trace import untraced_paths

    untraced = untraced_paths(core, paths)
    if not untraced:
        return {}
    unavailable = ""
    if backend is None:
        from plumb.judgment import JudgmentUnavailable, get_backend

        try:
            backend = get_backend(core, hook=True)
        except JudgmentUnavailable as exc:  # INT-029: said, never answered by rules
            unavailable = str(exc)
    index = core.index()
    out: dict[str, Proposal] = {}
    for path in untraced:
        found = candidates(core, path)
        if not found:
            out[path] = Proposal(path=path, backend=getattr(backend, "name", "none"),
                                 reason="no requirement near it",
                                 line=f"plumb: {path}: no requirement owns it; record a new "
                                      "SR (proposed)")
            continue
        if backend is None:
            out[path] = Proposal(path=path, candidates=tuple(found), backend="none",
                                 reason=f"judging unavailable: {unavailable}",
                                 line=f"plumb: {path}: candidates {', '.join(found)}; judging "
                                      f"unavailable: {unavailable}; read it back and choose")
            continue
        options = {f"{i}: {index[i].title}": i for i in found}
        judgment = backend.choose(f"Which requirement owns the change to {path}?",
                                  list(options), subject=path, context=_context(core, path))
        chosen = options.get(judgment.verdict)
        confidence = judgment.confidence
        reason = "; ".join(judgment.reasons)
        if chosen is None:
            out[path] = Proposal(path=path, candidates=tuple(found),
                                 backend=judgment.backend, reason=reason or
                                 "no judgments available",
                                 line=f"plumb: {path}: candidates {', '.join(found)}; no "
                                      "judgments available, read it back and choose")
            continue
        out[path] = Proposal(
            path=path, proposed=chosen, candidates=tuple(found), confidence=confidence,
            backend=judgment.backend, reason=reason,
            line=f"plumb: {path}: {chosen} may own this (proposed); read it back and link it, "
                 "or record a new SR")
    return out


def diff_serves(core: Core, sr_ids: Sequence[str], paths: Sequence[str], *,
                backend: Any = None) -> list[str]:
    """One warning line per claimed SR the backend judges, with high confidence, not served
    by the diff's paths. Never blocks; with no judge it says nothing."""
    index = core.index()
    wanted = [i for i in sr_ids if i in index and index[i].kind == "requirement"]
    if not wanted or not paths:
        return []
    if backend is None:
        from plumb.judgment import JudgmentUnavailable, get_backend

        try:
            backend = get_backend(core, hook=True)
        except JudgmentUnavailable as exc:
            return [f"plumb: judging unavailable: {exc}"]
    shown = ", ".join(list(paths)[:6])
    out: list[str] = []
    for record_id in wanted:
        record = index[record_id]
        context = (f"{record_id}: {record.title}\n{record.fields.get('statement') or ''}\n"
                   f"changed paths: {shown}")
        judgment = backend.ask(f"Does this diff serve {record_id}?", context,
                               subject=record_id, action="ownership")
        if judgment.verdict == "no" and judgment.confidence >= WARN_CONFIDENCE:
            out.append(f"plumb: warning: {record_id} may not be served by {shown}")
    return out


# --------------------------------------------------------------------------- test nodes


def _tests_in(core: Core, path: str) -> list[tuple[str, str]]:
    """``(name, name and docstring words)`` of each test function in a test file."""
    try:
        tree = ast.parse((core.root / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test"):
            doc = ast.get_docstring(node) or ""
            out.append((node.name, node.name.replace("_", " ") + " " + doc))
    return out


def node_proposals(core: Core, ids: Sequence[str]) -> list[Proposal]:
    """For each ``verified_by`` link of ``ids`` naming a bare test file and an example: the
    test node whose name and docstring overlap the example best, when its lead is clear."""
    from plumb.judgment.textjudge import overlap_share, stems

    index = core.index()
    out: list[Proposal] = []
    for record_id in ids:
        record = index.get(record_id)
        if record is None or record.kind != "requirement":
            continue
        examples = {e.id: e for e in record.examples}
        for link in record.links:
            path = link.target.path
            if link.kind != "verified_by" or not path or link.target.test or not link.example:
                continue
            example = examples.get(link.example)
            if example is None:
                continue
            wanted = stems(" ".join((example.given, example.when, example.then,
                                     example.criterion)))
            scored = sorted(((overlap_share(stems(words), wanted), name)
                             for name, words in _tests_in(core, path)), reverse=True)
            if not scored or scored[0][0] <= 0:
                continue
            lead = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0.0)
            if len(scored) > 1 and lead < 0.1:
                continue
            node = f"{path}::{scored[0][1]}"
            out.append(Proposal(
                path=path, proposed=node, confidence=round(scored[0][0], 3),
                backend="name-overlap", reason=f"name overlap {scored[0][0]:.2f}",
                line=f"plumb: hint: {record_id} {link.example} is verified by the whole file "
                     f"{path}; proposed node {node} (not written)"))
    return out


def proposals_map(items: Sequence[Proposal]) -> Mapping[str, Proposal]:
    return {p.path: p for p in items}
