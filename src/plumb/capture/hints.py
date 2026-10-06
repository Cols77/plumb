"""Hidden-dependency hints (R12.4; sp2 10.2, SR-045) and proposed test nodes (sp2 10.1),
as ready lines for ``plumb drift``, the brief and ``/plumb review``.

When a confirmed record (or one the owner confirmed before and that is now edited), or an
authoritative document (``hints.authoritative_docs``), changes, a bounded scan (at most
``hints.hidden_deps_max`` candidates, at most ``hints.hidden_deps_s`` seconds) proposes the
records with no link to it whose text overlaps its changed terms; the backend confirms each
with one ``ask``. With the heuristic, the overlap alone proposes them (degraded). Hints are
never staleness marks, never edges, and never interrupt.
"""

from __future__ import annotations

import fnmatch
import subprocess
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plumb.api import Core

MIN_SHARED = 2


def _glob(pattern: str, path: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (
        pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"))


def _head_text(core: Core, path: str) -> str:
    try:
        result = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=core.root,
                                capture_output=True, timeout=1.0, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def _now_text(core: Core, path: str) -> str:
    try:
        return (core.root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def changed_paths(core: Core) -> list[str]:
    """Working-tree changes (tracked and untracked), for ``plumb drift``."""
    try:
        result = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                                cwd=core.root, capture_output=True, timeout=2.0, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    skip = False
    for entry in result.stdout.decode("utf-8", errors="replace").split("\0"):
        if skip:
            skip = False
            continue
        if len(entry) < 4:
            continue
        if "R" in entry[:2] or "C" in entry[:2]:
            skip = True
        out.append(entry[3:])
    return out


def _subjects(core: Core, changed: Sequence[str]) -> list[tuple[str, str]]:
    """``(subject, path)`` of the changed confirmed records and authoritative documents."""
    index = core.index()
    by_path = {r.path: r.id for r in index.values()}
    statuses = core.status()
    docs = tuple(core.config.hints.authoritative_docs)
    out: list[tuple[str, str]] = []
    for item in changed:
        record_id = item if item in index else by_path.get(item)
        if record_id is not None:
            if statuses[record_id].confirmation in ("confirmed", "unconfirmed-edit"):
                out.append((record_id, index[record_id].path))
        elif any(_glob(d, item) for d in docs):
            out.append((item, item))
    return out


def hidden_dependency_hints(core: Core, changed: Sequence[str], *,
                            backend: Any = None) -> list[str]:
    from plumb.judgment.textjudge import record_subject_text, stems

    subjects = _subjects(core, changed)
    if not subjects:
        return []
    config = core.config.hints
    deadline = time.monotonic() + float(config.hidden_deps_s)
    if backend is None:
        from plumb.judgment import get_backend

        backend = get_backend(core, hook=True)
    index = core.index()
    lines: list[str] = []
    for subject, path in subjects:
        before, after = stems(_head_text(core, path)), stems(_now_text(core, path))
        # a record: what it is about; a long document: only the terms its change moved
        moved = (before | after) if subject in index else ((before ^ after) or after)
        linked = {subject}
        record = index.get(subject)
        if record is not None:
            linked |= {link.target.record for link in record.links if link.target.record}
        linked |= {r.id for r in index.values()
                   if any(link.target.record == subject or link.target.path == path
                          for link in r.links)}
        scored = []
        for other in index.values():
            if other.id in linked:
                continue
            shared = moved & stems(record_subject_text(other))
            if len(shared) >= MIN_SHARED:
                scored.append((len(shared), other.id, sorted(shared)))
        scored.sort(key=lambda item: (-item[0], item[1]))
        for _, other_id, shared in scored[: int(config.hidden_deps_max)]:
            if time.monotonic() > deadline:
                return lines
            judgment = backend.ask(
                f"Does {other_id} depend on what changed in {subject}?",
                f"changed terms: {', '.join(shared[:12])}\n{other_id}: "
                f"{record_subject_text(index[other_id])}", subject=other_id,
                action="dependency")
            if judgment.verdict == "no":
                continue
            terms = ", ".join(shared[:3])
            how = "" if judgment.verdict == "yes" else f" (by shared terms: {terms})"
            lines.append(f"plumb: hint: {other_id} may depend on the change to {subject} "
                         f"(no link){how}")
    return lines


NODE_LINES = 5


def drift_hints(core: Core, changed: Sequence[str], *, backend: Any = None,
                all_nodes: bool = False) -> list[str]:
    """Hidden-dependency hints and proposed test nodes for the changed records and paths
    (with ``all_nodes``, for every requirement, at most ``NODE_LINES`` lines)."""
    from plumb.capture.ownership import node_proposals

    index = core.index()
    by_path = {r.path: r.id for r in index.values()}
    touched = [i if i in index else by_path.get(i) for i in changed]
    ids = [i for i in dict.fromkeys(touched) if i]
    if all_nodes:
        ids = sorted(index)
    lines = hidden_dependency_hints(core, changed, backend=backend)
    nodes = [p.line for p in node_proposals(core, ids)]
    if len(nodes) > NODE_LINES:
        nodes = nodes[:NODE_LINES] + [f"plumb: hint: +{len(nodes) - NODE_LINES} more proposed "
                                      "test nodes (plumb drift --json)"]
    return lines + nodes
