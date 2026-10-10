"""The function-to-tests map (SR-110): which functions each test executed when it was recorded.

Stored in SQLite (``.plumb/cache/funcmap.sqlite``, a cache like the test map: gitignored, rebuilt
by ``plumb tests map --coverage``). Tables:

- ``tests(node, file, closure_digest, recorded_at, env_key)``: one row per recorded test node.
  An entry is stale when the test file's import-closure digest differs from the recorded one,
  and it counts only under the environment key it was recorded with.
- ``funcs(path, qualname, hash)``: every function of every measured source file, with the hash
  it had when last recorded. The hash is that of the function's syntax tree (docstring and
  decorators included), so a reformat or a comment does not change it. The pseudo function
  ``<module>`` is the rest of the file (module and class level code, signatures, imports).
- ``hits(func, test)``: the function ran in the test.

``functions_changed`` compares the files as they are now with what was recorded: a function
whose hash differs is ``changed``; one the record has never seen is ``new``; a change in the
module part is the ``<module>`` function (every test importing the file ran it).
"""

from __future__ import annotations

import ast
import sqlite3
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from plumb.normalize import sha256_text

MODULE = "<module>"
SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY, node TEXT UNIQUE NOT NULL, file TEXT NOT NULL,
    closure_digest TEXT NOT NULL, recorded_at TEXT NOT NULL, env_key TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS funcs (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL, qualname TEXT NOT NULL, hash TEXT NOT NULL,
    UNIQUE (path, qualname));
CREATE TABLE IF NOT EXISTS hits (
    func INTEGER NOT NULL, test INTEGER NOT NULL, PRIMARY KEY (func, test));
CREATE INDEX IF NOT EXISTS hits_by_test ON hits (test);
CREATE INDEX IF NOT EXISTS tests_by_file ON tests (file);
"""
_COMPOUND = ("body", "orelse", "finalbody")


class ChangedFunction(NamedTuple):
    path: str
    qualname: str
    kind: str  # "changed" | "new"


def default_path(core: Any) -> Path:
    return Path(core.paths.cache) / "funcmap.sqlite"


def _definitions(body: Sequence[ast.stmt], prefix: str,
                 out: list[tuple[str, ast.AST]]) -> None:
    """Functions reachable from the module and class bodies (also under if/try/with)."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((prefix + stmt.name, stmt))
        elif isinstance(stmt, ast.ClassDef):
            _definitions(stmt.body, prefix + stmt.name + ".", out)
        elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For,
                               ast.AsyncFor, ast.While)):
            for name in _COMPOUND:
                _definitions(getattr(stmt, name, []) or [], prefix, out)
            for handler in getattr(stmt, "handlers", []) or []:
                _definitions(handler.body, prefix, out)


class _WithoutFunctions(ast.NodeTransformer):
    """The rest of a file: every function definition removed (each has its own hash)."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return None

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]  # noqa: N815


def _parse(root: Path, rel: str) -> ast.Module | None:
    try:
        text = (Path(root) / rel).read_bytes().decode("utf-8")
        return ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None


def analyse_file(root: Path,
                 rel: str) -> tuple[dict[str, str], list[tuple[int, int, str]]] | None:
    """``({qualname: hash}, [(first_line, last_line, qualname)])`` of a source file (the body
    lines of each function; the ``<module>`` hash covers everything outside function definitions),
    or None when the file cannot be read or parsed."""
    tree = _parse(root, rel)
    if tree is None:
        return None
    found: list[tuple[str, ast.AST]] = []
    _definitions(tree.body, "", found)
    hashes: dict[str, str] = {}
    spans: list[tuple[int, int, str]] = []
    for qualname, node in found:
        hashes[qualname] = sha256_text(ast.dump(node))
        body = getattr(node, "body", [])
        if body and getattr(node, "end_lineno", None):
            spans.append((body[0].lineno, int(node.end_lineno), qualname))  # type: ignore
    hashes[MODULE] = sha256_text(ast.dump(_WithoutFunctions().visit(tree)))
    return hashes, spans


def file_functions(root: Path, rel: str) -> dict[str, str]:
    """``{qualname: hash}`` of the functions in a file now, plus ``<module>`` (empty when the
    file is missing or does not parse)."""
    got = analyse_file(root, rel)
    return got[0] if got else {}


def functions_of_lines(spans: Sequence[tuple[int, int, str]], lines: Iterable[int]) -> set[str]:
    """The innermost function containing each executed line (module-level lines: none)."""
    out: set[str] = set()
    ordered = sorted(spans, key=lambda s: s[1] - s[0])  # innermost (smallest) first
    for line in lines:
        for first, last, qualname in ordered:
            if first <= line <= last:
                out.add(qualname)
                break
    return out


class FuncMap:
    def __init__(self, path: Path, root: Path) -> None:
        self.path = Path(path)
        self.root = Path(root)
        self._db: sqlite3.Connection | None = None

    # -- storage
    @classmethod
    def open(cls, core: Any) -> FuncMap:
        return cls(default_path(core), Path(core.root))

    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path))
            db.executescript(_SCHEMA)
            row = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
            if row is not None and row[0] != str(SCHEMA_VERSION):
                for table in ("hits", "funcs", "tests"):
                    db.execute(f"DELETE FROM {table}")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)",
                       (str(SCHEMA_VERSION),))
            db.commit()
            self._db = db
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.commit()
            self._db.close()
            self._db = None

    def commit(self) -> None:
        if self._db is not None:
            self._db.commit()

    def clear(self) -> None:
        for table in ("hits", "funcs", "tests"):
            self.db.execute(f"DELETE FROM {table}")
        self.db.commit()

    # -- writing
    def register_file(self, rel: str, hashes: Mapping[str, str] | None = None) -> bool:
        """Store the current hash of every function of ``rel``; drop functions it lost."""
        if hashes is None:
            hashes = file_functions(self.root, rel)
        if not hashes:
            return False
        db = self.db
        for qualname, digest in hashes.items():
            db.execute("INSERT INTO funcs (path, qualname, hash) VALUES (?, ?, ?) "
                       "ON CONFLICT (path, qualname) DO UPDATE SET hash = excluded.hash",
                       (rel, qualname, digest))
        keep = set(hashes)
        for fid, qualname in db.execute("SELECT id, qualname FROM funcs WHERE path = ?",
                                        (rel,)).fetchall():
            if qualname not in keep:
                db.execute("DELETE FROM hits WHERE func = ?", (fid,))
                db.execute("DELETE FROM funcs WHERE id = ?", (fid,))
        return True

    def record_test(self, node: str, test_file: str, closure_digest: str, env_key: str,
                    executed: Iterable[tuple[str, str]], recorded_at: str | None = None) -> None:
        """Replace the record of one test node by the functions it executed."""
        db = self.db
        stamp = recorded_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.execute("INSERT INTO tests (node, file, closure_digest, recorded_at, env_key) "
                   "VALUES (?, ?, ?, ?, ?) ON CONFLICT (node) DO UPDATE SET file = excluded.file,"
                   " closure_digest = excluded.closure_digest, recorded_at = excluded.recorded_at,"
                   " env_key = excluded.env_key", (node, test_file, closure_digest, stamp, env_key))
        tid = db.execute("SELECT id FROM tests WHERE node = ?", (node,)).fetchone()[0]
        db.execute("DELETE FROM hits WHERE test = ?", (tid,))
        for path, qualname in executed:
            row = db.execute("SELECT id FROM funcs WHERE path = ? AND qualname = ?",
                             (path, qualname)).fetchone()
            if row is not None:
                db.execute("INSERT OR IGNORE INTO hits VALUES (?, ?)", (row[0], tid))

    def forget_tests(self, nodes: Iterable[str]) -> None:
        for node in nodes:
            row = self.db.execute("SELECT id FROM tests WHERE node = ?", (node,)).fetchone()
            if row is not None:
                self.db.execute("DELETE FROM hits WHERE test = ?", (row[0],))
                self.db.execute("DELETE FROM tests WHERE id = ?", (row[0],))

    # -- reading
    def tests_executing(self, path: str, qualname: str, env_key: str | None = None) -> list[str]:
        sql = ("SELECT t.node FROM hits h JOIN funcs f ON f.id = h.func "
               "JOIN tests t ON t.id = h.test WHERE f.path = ? AND f.qualname = ?")
        args: list[Any] = [path, qualname]
        if env_key is not None:
            sql += " AND t.env_key = ?"
            args.append(env_key)
        return sorted(r[0] for r in self.db.execute(sql, args))

    def is_recorded(self, path: str, env_key: str | None = None) -> bool:
        """Some recorded test executed a function of ``path`` (under ``env_key``)."""
        sql = ("SELECT 1 FROM hits h JOIN funcs f ON f.id = h.func JOIN tests t ON t.id = h.test"
               " WHERE f.path = ?")
        args: list[Any] = [path]
        if env_key is not None:
            sql += " AND t.env_key = ?"
            args.append(env_key)
        return self.db.execute(sql + " LIMIT 1", args).fetchone() is not None

    def is_recorded_anywhere(self, env_key: str | None = None) -> bool:
        sql = "SELECT 1 FROM tests"
        args: list[Any] = []
        if env_key is not None:
            sql += " WHERE env_key = ?"
            args.append(env_key)
        return self.db.execute(sql + " LIMIT 1", args).fetchone() is not None

    def functions_changed(self, paths: Iterable[str]) -> list[ChangedFunction]:
        """Functions of ``paths`` whose current hash differs from the recorded one, or that
        the record has never seen (a file the record has never seen has no entries)."""
        out: list[ChangedFunction] = []
        for rel in paths:
            recorded = dict(self.db.execute(
                "SELECT qualname, hash FROM funcs WHERE path = ?", (rel,)).fetchall())
            if not recorded:
                continue
            for qualname, digest in sorted(file_functions(self.root, rel).items()):
                if qualname not in recorded:
                    out.append(ChangedFunction(rel, qualname, "new"))
                elif recorded[qualname] != digest:
                    out.append(ChangedFunction(rel, qualname, "changed"))
        return out

    def entry(self, node: str) -> tuple[str, str, str] | None:
        row = self.db.execute("SELECT file, closure_digest, env_key FROM tests WHERE node = ?",
                              (node,)).fetchone()
        return None if row is None else (row[0], row[1], row[2])

    def fresh_nodes(self, digests: Mapping[str, str | None], env_key: str) -> set[str]:
        """Recorded nodes whose file's closure digest is still the recorded one (under
        ``env_key``): their record needs no refresh."""
        out: set[str] = set()
        for node, file, digest in self.db.execute(
                "SELECT node, file, closure_digest FROM tests WHERE env_key = ?", (env_key,)):
            if digests.get(file) == digest:
                out.add(node)
        return out

    def stats(self) -> dict[str, int]:
        db = self.db
        return {"tests": db.execute("SELECT COUNT(*) FROM tests").fetchone()[0],
                "funcs": db.execute("SELECT COUNT(*) FROM funcs").fetchone()[0],
                "hits": db.execute("SELECT COUNT(*) FROM hits").fetchone()[0]}


# -- recording from coverage data
def combine_data_files(files: Sequence[str], target: str) -> Any:
    """Combine the per-process coverage data files into ``target`` (contexts are kept) and
    return the combined ``CoverageData``."""
    from coverage import CoverageData

    combined = CoverageData(basename=target)
    combined.erase()
    for name in files:
        part = CoverageData(basename=name)
        part.read()
        combined.update(part)
    combined.write()
    return combined


def executed_functions(root: Path, data: Any, *,
                       skip_file: Any = None) -> tuple[dict[str, set[tuple[str, str]]],
                                                       dict[str, dict[str, str]]]:
    """``({context: {(path, qualname)}}, {path: {qualname: hash}})`` from coverage data: the
    functions each context (test node) executed, and every measured file's function hashes.
    ``skip_file(rel)`` names files left out (test modules)."""
    root = Path(root).resolve()
    executed: dict[str, set[tuple[str, str]]] = {}
    hashes: dict[str, dict[str, str]] = {}
    for name in data.measured_files():
        try:
            rel = Path(name).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if skip_file is not None and skip_file(rel):
            continue
        got = analyse_file(root, rel)
        if got is None:
            continue
        hashes[rel], spans = got
        by_context: dict[str, set[int]] = {}
        for line, contexts in (data.contexts_by_lineno(name) or {}).items():
            for context in contexts:
                if context:
                    by_context.setdefault(context, set()).add(line)
        for context, lines in by_context.items():
            for qualname in functions_of_lines(spans, lines):
                executed.setdefault(context, set()).add((rel, qualname))
    return executed, hashes


def ingest_coverage(fm: FuncMap, data: Any, nodes: Mapping[str, str],
                    digests: Mapping[str, str | None], env_key: str, *,
                    skip_file: Any = None) -> list[str]:
    """Record the test nodes in ``nodes`` (``{node: test file}``) from combined coverage
    ``data``; a node that executed nothing measured is recorded with no hits (so it is not
    stale). Returns the recorded nodes."""
    executed, hashes = executed_functions(fm.root, data, skip_file=skip_file)
    for rel, table in hashes.items():
        fm.register_file(rel, table)
    recorded: list[str] = []
    for node, test_file in sorted(nodes.items()):
        digest = digests.get(test_file)
        if digest is None:
            continue
        fm.record_test(node, test_file, digest, env_key, executed.get(node, ()))
        recorded.append(node)
    fm.commit()
    return recorded
