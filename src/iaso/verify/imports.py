"""Python import edges and transitive import closures (spec 7.1).

Extracted and simplified from pi-agent-factory's ``substrate/codemap/imports.py``
(``_import_edges``, ``_resolve_import``, ``_closure_walk``): resolution is anchored on the
repository root and each configured source directory, ``from X import name`` also resolves
``X/name.py`` submodules, a dotted import also reaches its parent packages, and anything
that does not resolve to a file inside the repository is ignored.
"""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

Edge = tuple[str, int, tuple[str, ...]]


def import_edges(source: str) -> list[Edge]:
    """``(module, level, names)`` for every import statement; ``[]`` when unparsable."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return edges_of(tree)


def edges_of(tree: ast.AST) -> list[Edge]:
    edges: list[Edge] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((alias.name, 0, ()))
        elif isinstance(node, ast.ImportFrom):
            names = tuple(a.name for a in node.names if a.name != "*")
            edges.append((node.module or "", node.level or 0, names))
    return edges


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _module_file(anchor: Path, parts: Sequence[str]) -> Path | None:
    if not parts:
        init = anchor / "__init__.py"
        return init if _is_file(init) else None
    base = anchor.joinpath(*parts)
    for cand in (base.with_name(base.name + ".py"), base / "__init__.py"):
        if _is_file(cand):
            return cand
    return None


def resolve_edge(root: Path, origin: str, edge: Edge,
                 source_dirs: Sequence[str]) -> set[str]:
    """Repository-relative files one import statement of ``origin`` reaches."""
    module, level, names = edge
    parts = [p for p in module.split(".") if p] if module else []
    if level > 0:
        anchor = (root / origin).parent
        for _ in range(level - 1):
            anchor = anchor.parent
        anchors = [anchor]
    else:
        anchors = [root, *(root / d for d in source_dirs)]
    found: set[Path] = set()
    for anchor in anchors:
        target = _module_file(anchor, parts)
        hit = False
        if target is not None:
            found.add(target)
            hit = True
            if level == 0:  # importing a.b.c also runs a/__init__ and a/b/__init__
                for i in range(1, len(parts)):
                    init = anchor.joinpath(*parts[:i]) / "__init__.py"
                    if _is_file(init):
                        found.add(init)
        for name in names:
            sub = _module_file(anchor, [*parts, name])
            if sub is not None:
                found.add(sub)
                hit = True
        if hit:
            break
    out: set[str] = set()
    root_resolved = root.resolve()
    for path in found:
        try:
            rel = path.resolve().relative_to(root_resolved).as_posix()
        except (ValueError, OSError):
            continue
        if rel != origin:
            out.add(rel)
    return out


def known_files(root: Path, known: Iterable[str],
                scanned_dirs: Sequence[str]) -> Callable[[str], bool]:
    """A memoized ``exists(rel)``: answers from ``known`` (repository-relative ``.py`` paths)
    for every path under ``scanned_dirs``, and from the filesystem elsewhere."""
    known_set = frozenset(known)
    prefixes = tuple(d.strip("/") + "/" for d in scanned_dirs if d.strip("/") not in ("", "."))
    memo: dict[str, bool] = {}

    def exists(rel: str) -> bool:
        hit = memo.get(rel)
        if hit is None:
            if rel in known_set or rel.startswith(prefixes):
                hit = rel in known_set
            else:
                hit = _is_file(root / rel)
            memo[rel] = hit
        return hit

    return exists


def _join(*parts: str) -> str:
    return "/".join(p for p in parts if p)


def _module_rel(anchor: str, parts: Sequence[str], exists: Callable[[str], bool]) -> str | None:
    if not parts:
        init = _join(anchor, "__init__.py")
        return init if exists(init) else None
    base = _join(anchor, *parts)
    for cand in (base + ".py", base + "/__init__.py"):
        if exists(cand):
            return cand
    return None


def resolve_edge_rel(origin: str, edge: Edge, source_dirs: Sequence[str],
                     exists: Callable[[str], bool]) -> set[str]:
    """``resolve_edge`` on repository-relative POSIX strings, with ``exists`` (see
    ``known_files``) answering existence: no path objects, no stat calls for scanned files.
    Used by the test map, whose re-resolution of every edge must stay cheap (spec 10)."""
    module, level, names = edge
    parts = [p for p in module.split(".") if p] if module else []
    if level > 0:
        anchor_parts = origin.split("/")[:-1]
        if level - 1 > len(anchor_parts):
            return set()
        anchors = ["/".join(anchor_parts[: len(anchor_parts) - (level - 1)])]
    else:
        anchors = ["", *(d.strip("/") for d in source_dirs if d.strip("/") not in ("", "."))]
    found: set[str] = set()
    for anchor in anchors:
        target = _module_rel(anchor, parts, exists)
        hit = False
        if target is not None:
            found.add(target)
            hit = True
            if level == 0:  # importing a.b.c also runs a/__init__ and a/b/__init__
                for i in range(1, len(parts)):
                    init = _join(anchor, *parts[:i], "__init__.py")
                    if exists(init):
                        found.add(init)
        for name in names:
            sub = _module_rel(anchor, [*parts, name], exists)
            if sub is not None:
                found.add(sub)
                hit = True
        if hit:
            break
    found.discard(origin)
    return found


def direct_imports(root: Path, rel: str, source_dirs: Sequence[str],
                   edges: Iterable[Edge] | None = None) -> set[str]:
    """Files ``rel`` imports directly (repository-relative POSIX paths)."""
    root = Path(root)
    if edges is None:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return set()
        edges = import_edges(text)
    out: set[str] = set()
    for edge in edges:
        out |= resolve_edge(root, rel, tuple(edge), source_dirs)  # type: ignore[arg-type]
    return out


def closure(root: Path, rel: str, source_dirs: Sequence[str],
            direct: Callable[[str], Iterable[str]] | None = None) -> dict[str, int]:
    """Every file transitively imported from ``rel`` with its BFS depth (``rel`` is 0)."""
    root = Path(root)
    if direct is None:
        def direct(path: str) -> Iterable[str]:
            return direct_imports(root, path, source_dirs)
    depths: dict[str, int] = {rel: 0}
    queue: deque[str] = deque([rel])
    while queue:
        cur = queue.popleft()
        for nxt in sorted(direct(cur)):
            if nxt not in depths:
                depths[nxt] = depths[cur] + 1
                queue.append(nxt)
    return depths
