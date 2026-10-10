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
import contextlib
import functools
import hashlib
import json
import os
import re
import sys
import textwrap
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import Record, Target
from plumb.normalize import file_digest, sha256_text

_PARAM_ID = re.compile(r"\[.*\]$")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")  # the line breaks ast counts
# parsed modules keyed by the file's raw-bytes digest (never by size and mtime, which a quick
# same-size rewrite can leave unchanged): one parse per content per process, however many
# symbol or test-node ends a file holds (an import pins hundreds of them)
_PARSED: dict[str, tuple[list[str], ast.Module] | None] = {}
# The hooks' snapshot reads every link end each turn; inside ``stat_cached`` a file end's hash
# is reused while the file's size, mtime, ctime and inode are unchanged (git's index check),
# from ``.plumb/cache/hashes.json``. A file modified within ``_RACY_S`` of the check is never
# cached, so a same-size rewrite within the clock's resolution is still seen. validate, drift
# and the merge boundary never enter the cache: they hash every end exactly.
_RACY_S = 2.0
_STAT_CACHE: dict[str, Any] | None = None  # {"root": ..., "entries": {key: [stat..., hash]}}
# bumped whenever what the open block remembers of the link ends is dropped; the core keeps
# its statuses only while this and its record index and events are unchanged
_GENERATION = 0


@functools.lru_cache(maxsize=16384)
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
    parts = [p for p in text.split("/") if p and p != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def hash_path(root: Path, raw: str) -> str | None:
    """Hash of a repository file, or None when it is missing, not a file, or outside."""
    rel = clean_rel_path(raw)
    if rel is None:
        return None
    full = Path(root) / rel
    cache = _STAT_CACHE
    if cache is None:
        return _file_digest_of(full)
    files = cache["digests"]  # one hook process: a file is read once for its whole-file end
    memo_key = str(full)
    if memo_key not in files:
        files[memo_key] = _file_digest_of(full)
    return files[memo_key]


def _file_digest_of(full: Path) -> str | None:
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
    cache = _STAT_CACHE
    if cache is not None:  # one hook process: a file's symbol and test ends share one read
        files = cache["parsed"]
        memo_key = str(full)
        if memo_key not in files:
            files[memo_key] = _parse_bytes(full)
        return files[memo_key]
    return _parse_bytes(full)


def _parse_bytes(full: Path) -> tuple[list[str], ast.Module] | None:
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


def _cache_file(root: Path) -> Path:
    return Path(root) / ".plumb" / "cache" / "hashes.json"


@contextlib.contextmanager
def stat_cached(root: Path) -> Iterator[None]:
    """Reuse file-end hashes from ``.plumb/cache/hashes.json`` while the block runs, and save
    what it learned when it ends (the hooks' snapshot only; see ``_STAT_CACHE``)."""
    global _STAT_CACHE, _GENERATION
    if _STAT_CACHE is not None:  # nested: the outer block owns the cache
        yield
        return
    try:
        data = json.loads(_cache_file(root).read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
    except (OSError, ValueError):
        entries = None
    _STAT_CACHE = {"root": Path(root).resolve(), "same": {}, "dirty": False, "memo": {},
                   "parsed": {}, "digests": {}, "stamps": {},
                   "entries": entries if isinstance(entries, dict) else {}}
    _GENERATION += 1
    try:
        yield
    finally:
        flush_stat_cache()
        _STAT_CACHE = None
        _GENERATION += 1


def _open_for_hook() -> None:
    """Open ``stat_cached`` for the hook running in this process, at the first hash (the hook
    runner only names the root: this module is not imported before a hook needs it)."""
    hookio = sys.modules.get("plumb.hosts.claude_code.hookio")
    root = getattr(hookio, "STAT_CACHE_ROOT", None)
    if root is None or getattr(hookio, "STAT_CACHE_STACK", None) is not None:
        return
    stack = contextlib.ExitStack()
    try:
        stack.enter_context(stat_cached(root))
    except Exception:  # noqa: BLE001 - no cache never blocks the turn
        return
    hookio.STAT_CACHE_STACK = stack  # the hook runner closes it (saving what was learned)


def ends_memo_active() -> bool:
    """True inside ``stat_cached``: link-end hashes are then fixed for the process (until
    ``forget_ends``), so the core may keep what it derived from them."""
    if _STAT_CACHE is None:
        _open_for_hook()
    return _STAT_CACHE is not None


def ends_generation() -> int:
    """Changes whenever the remembered link-end hashes are dropped or a block opens/closes."""
    return _GENERATION


def forget_ends() -> None:
    """Drop what the open block remembers of the files (a code file changed in this process)."""
    global _GENERATION
    cache = _STAT_CACHE
    if cache is not None:
        cache["memo"].clear()
        cache["parsed"].clear()
        cache["digests"].clear()
        cache["stamps"].clear()
    _GENERATION += 1


def flush_stat_cache() -> None:
    """Save what the open ``stat_cached`` block learned (the hook watchdog calls this just
    before it ends the process, so a hook too slow to finish still warms the next one)."""
    cache = _STAT_CACHE
    if cache is None or not cache["dirty"]:
        return
    path = _cache_file(cache["root"])
    try:
        cache["dirty"] = False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"entries": dict(cache["entries"])}), encoding="utf-8")
        os.replace(tmp, path)  # concurrent hooks: the last writer wins, never torn
    except (OSError, RuntimeError, ValueError):
        pass  # a cache that cannot be saved costs time, never correctness


def _hash_file_end(root: Path, target: Target) -> str | None:
    if target.test:
        return hash_test_node(root, target.test)
    if target.path and target.symbol:
        return hash_symbol(root, target.path, target.symbol)
    path = target_path(target)
    if path is None:
        return None
    return hash_path(root, path)


def _cached_file_end(root: Path, target: Target) -> str | None:
    cache = _STAT_CACHE
    if cache is None:
        return _hash_file_end(root, target)
    memo_key = (str(root), target.test, target.path, target.symbol)
    memo = cache["memo"]  # one hook process: the brief and the snapshot ask for the same ends
    if memo_key in memo:
        return memo[memo_key]
    digest = memo[memo_key] = _stat_cached_end(cache, root, target)
    return digest


def _file_stamp(cache: dict[str, Any], full: Path) -> list[int] | None:
    """A file's [size, mtime, ctime, inode], stat'ed once per process (symbol and test ends
    of one file share it); None when it cannot be stat'ed."""
    stamps = cache["stamps"]
    key = str(full)
    if key not in stamps:
        try:
            st = os.stat(full)
            stamps[key] = [st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino]
        except OSError:
            stamps[key] = None
    return stamps[key]


def _stat_cached_end(cache: dict[str, Any], root: Path, target: Target) -> str | None:
    rel = clean_rel_path(target_path(target) or "")
    if rel is None:
        return _hash_file_end(root, target)
    same = cache["same"].get(str(root))
    if same is None:  # the hooks pass the root in more than one spelling
        same = cache["same"][str(root)] = Path(root).resolve() == cache["root"]
    if not same:
        return _hash_file_end(root, target)
    stamp = _file_stamp(cache, Path(root) / rel)
    if stamp is None:
        return _hash_file_end(root, target)
    mtime_ns = stamp[1]
    key = f"{target.test or ''}|{rel}|{target.symbol or ''}"
    hit = cache["entries"].get(key)
    if isinstance(hit, list) and len(hit) == 5 and hit[:4] == stamp:
        return hit[4]
    digest = _hash_file_end(root, target)
    if time.time() - mtime_ns / 1e9 > _RACY_S:
        cache["entries"][key] = [*stamp, digest]
        cache["dirty"] = True
    return digest


def hash_target(root: Path, index: Mapping[str, Record], target: Target) -> str | None:
    """Current hash of a link end, or None when it does not exist (dangling)."""
    if target.record is not None:
        record = index.get(target.record)
        return record.hash if record is not None else None
    if _STAT_CACHE is None:
        _open_for_hook()
    if _STAT_CACHE is not None:
        return _cached_file_end(root, target)
    if target.test:
        return hash_test_node(root, target.test)
    if target.path and target.symbol:
        return hash_symbol(root, target.path, target.symbol)
    path = target_path(target)
    if path is None:
        return None
    return hash_path(root, path)
