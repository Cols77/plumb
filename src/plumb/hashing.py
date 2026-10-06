"""Hashes of link ends (spec 5.4).

Records hash through ``model.record_hash``. Whole-file ends hash the file's normalized text
(raw bytes when it is not UTF-8). A Python symbol end (``path`` plus ``symbol``, written
``module:Qual.name`` or ``Qual.name``) hashes the normalized source segment of that one
definition, decorators included, found with ``ast``; a test-node end (``test:
path::name`` or ``path::Class::name``) hashes the test function's source the same way, with
parametrize ids (``[...]``) dropped. Edits elsewhere in the file leave such an end unchanged;
a definition that no longer exists (or a file that no longer parses) makes the end missing,
so its link dangles. Directories, globs and line numbers are never ends (concept 4.4).
"""

from __future__ import annotations

import ast
import hashlib
import re
import textwrap
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from plumb.contracts import Record, Target
from plumb.normalize import file_digest, sha256_text

_PARAM_ID = re.compile(r"\[.*\]$")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")  # the line breaks ast counts
# parsed modules keyed by the file's raw-bytes digest (never by size and mtime, which a quick
# same-size rewrite can leave unchanged): one parse per content per process, however many
# symbol or test-node ends a file holds (an import pins hundreds of them)
_PARSED: dict[str, tuple[list[str], ast.Module] | None] = {}


def clean_rel_path(raw: str) -> str | None:
    """A repository-relative POSIX path, or None when absolute or escaping the root.

    Root confinement mirrors pi-agent-factory's ``relations._confined_path``: an absolute
    path or any ``..`` segment is rejected on the string alone.
    """
    if not raw:
        return None
    text = raw.replace("\\", "/").strip()
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        return None
    parts = [p for p in PurePosixPath(text).parts if p != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def hash_path(root: Path, raw: str) -> str | None:
    """Hash of a repository file, or None when it is missing, not a file, or outside."""
    rel = clean_rel_path(raw)
    if rel is None:
        return None
    full = Path(root) / rel
    if not full.is_file():
        return None
    try:
        return file_digest(full)
    except OSError:
        return None


def symbol_qualname(symbol: str) -> str:
    """``module:Qual.name`` or ``Qual.name`` -> ``Qual.name``."""
    return symbol.rsplit(":", 1)[-1].strip()


def split_test_node(node: str) -> tuple[str, str]:
    """``path::Class::name[id]`` -> (``path``, ``Class.name``); parametrize ids dropped."""
    path, _, rest = node.partition("::")
    parts = [_PARAM_ID.sub("", part).strip() for part in rest.split("::")]
    return path, ".".join(p for p in parts if p)


def _parse(full: Path) -> tuple[list[str], ast.Module] | None:
    try:
        raw = full.read_bytes()
    except OSError:
        return None
    key = hashlib.sha256(raw).hexdigest()
    if key in _PARSED:
        return _PARSED[key]
    try:
        text = raw.decode("utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        parsed = None
    else:
        parsed = (_LINE_BREAK.split(text), tree)
    if len(_PARSED) > 512:
        _PARSED.clear()
    _PARSED[key] = parsed
    return parsed


def _defines(stmt: ast.stmt, name: str) -> bool:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return stmt.name == name
    if isinstance(stmt, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets)
    if isinstance(stmt, ast.AnnAssign):
        return isinstance(stmt.target, ast.Name) and stmt.target.id == name
    return False


def find_definition(tree: ast.Module, qualname: str) -> ast.stmt | None:
    """The definition ``Qual.name`` names (the last one, as Python binds it), or None."""
    body: list[ast.stmt] = tree.body
    node: ast.stmt | None = None
    for part in qualname.split("."):
        if not part:
            return None
        node = None
        for stmt in body:
            if _defines(stmt, part):
                node = stmt
        if node is None:
            return None
        body = getattr(node, "body", [])
    return node


def definition_source(root: Path, raw: str, qualname: str) -> str | None:
    """The normalized source of one definition in a repository file (decorators included)."""
    rel = clean_rel_path(raw)
    if rel is None or not qualname:
        return None
    full = Path(root) / rel
    if not full.is_file():
        return None
    parsed = _parse(full)
    if parsed is None:
        return None
    lines, tree = parsed
    node = find_definition(tree, qualname)
    if node is None or getattr(node, "end_lineno", None) is None:
        return None
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno] + [d.lineno for d in decorators])
    segment = "\n".join(lines[start - 1:node.end_lineno])
    return textwrap.dedent(segment)


def hash_symbol(root: Path, raw: str, symbol: str) -> str | None:
    source = definition_source(root, raw, symbol_qualname(symbol))
    return None if source is None else sha256_text(source)


def hash_test_node(root: Path, node: str) -> str | None:
    path, qualname = split_test_node(node)
    source = definition_source(root, path, qualname)
    return None if source is None else sha256_text(source)


def target_path(target: Target) -> str | None:
    """The file a non-record end lives in (``test`` nodes keep the part before ``::``)."""
    if target.path:
        return target.path
    if target.test:
        return target.test.split("::", 1)[0]
    return None


def hash_target(root: Path, index: Mapping[str, Record], target: Target) -> str | None:
    """Current hash of a link end, or None when it does not exist (dangling)."""
    if target.record is not None:
        record = index.get(target.record)
        return record.hash if record is not None else None
    if target.test:
        return hash_test_node(root, target.test)
    if target.path and target.symbol:
        return hash_symbol(root, target.path, target.symbol)
    path = target_path(target)
    if path is None:
        return None
    return hash_path(root, path)
