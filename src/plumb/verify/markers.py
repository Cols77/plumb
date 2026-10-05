"""``@pytest.mark.sr("SR-###")`` markers and test nodes, read with ``ast`` (spec 7.1).

Extracted from pi-agent-factory's ``coherence/register/markers.py`` (``collect_markers``):
the module is never imported, so its side effects never run. Markers are collected per test
node: a class marker and a module ``pytestmark`` apply to every test under them.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from plumb.normalize import sha256_text

_PARAM_ID = re.compile(r"\[.*\]$")


def _dotted(dec: ast.AST) -> str | None:
    node = dec.func if isinstance(dec, ast.Call) else dec
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts)) if parts else None


def _sr_ids(expr: ast.AST) -> set[str]:
    """SR ids of one marker expression (a call, or a list or tuple of calls)."""
    if isinstance(expr, (ast.List, ast.Tuple)):
        out: set[str] = set()
        for item in expr.elts:
            out |= _sr_ids(item)
        return out
    dotted = _dotted(expr)
    if dotted is None or not (dotted == "mark.sr" or dotted.endswith(".mark.sr")):
        return set()
    return {a.value for a in getattr(expr, "args", [])
            if isinstance(a, ast.Constant) and isinstance(a.value, str)}


def _decorated(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for dec in getattr(node, "decorator_list", []):
        out |= _sr_ids(dec)
    return out


def _module_marks(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets):
            out |= _sr_ids(stmt.value)
    return out


def walk_tests(tree: ast.Module, rel: str) -> Iterator[tuple[str, ast.AST, set[str]]]:
    """``(node_id, function_node, marks)`` for every test function or method."""

    def visit(body: list[ast.stmt], prefix: str,
              marks: set[str]) -> Iterator[tuple[str, ast.AST, set[str]]]:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name.startswith("test"):
                    yield f"{prefix}::{stmt.name}", stmt, marks | _decorated(stmt)
            elif isinstance(stmt, ast.ClassDef) and stmt.name.startswith("Test"):
                yield from visit(stmt.body, f"{prefix}::{stmt.name}", marks | _decorated(stmt))

    yield from visit(tree.body, rel, _module_marks(tree))


def _lf(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")


def parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(_lf(source))
    except (SyntaxError, ValueError):
        return None


def collect_markers(source: str, rel: str,
                    tree: ast.Module | None = None) -> dict[str, set[str]]:
    """``{node_id: {SR ids}}`` for every test node that carries at least one ``sr`` marker."""
    tree = tree or parse(source)
    if tree is None:
        return {}
    return {node_id: marks for node_id, _, marks in walk_tests(tree, rel) if marks}


def node_source_hash(source: str, func: ast.AST) -> str:
    """Normalized hash of one test function's source, decorators included."""
    lines = _lf(source).split("\n")
    decorators = getattr(func, "decorator_list", [])
    start = min([func.lineno, *(d.lineno for d in decorators)])  # type: ignore[attr-defined]
    end = func.end_lineno or func.lineno  # type: ignore[attr-defined]
    return sha256_text("\n".join(lines[start - 1:end]))


def test_nodes(source: str, rel: str, tree: ast.Module | None = None) -> dict[str, str]:
    """``{node_id: normalized source hash}`` for every test function or method."""
    tree = tree or parse(source)
    if tree is None:
        return {}
    return {node_id: node_source_hash(source, func) for node_id, func, _ in walk_tests(tree, rel)}


test_nodes.__test__ = False  # type: ignore[attr-defined]


def strip_param(node_id: str) -> str:
    """``path::test[1-2]`` -> ``path::test`` (parametrize ids carry no source)."""
    return _PARAM_ID.sub("", node_id)
