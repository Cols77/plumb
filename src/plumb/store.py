"""The record store: ``.plumb/<kind dir>/*.md`` (spec 4.2, 5.3, 5.8)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from typing import Any

from plumb.contracts import KIND_DIR, Record
from plumb.model import (
    RecordError,
    load_yaml,
    parse_record,
    record_from_parts,
    split_frontmatter,
)
from plumb.paths import PlumbPaths

INDEX_CACHE_VERSION = 2
# a file modified within this many seconds of the load is never trusted on size and mtime
# alone (a same-size rewrite within the clock's resolution would be missed), like git's racy
# index entries
_RACY_S = 2.0

FIELD_ORDER: Mapping[str, tuple[str, ...]] = {
    "intent": ("quote", "readback", "will", "wont", "assumptions", "mode", "source"),
    "requirement": ("feature", "statement", "domain", "examples"),
    "decision": ("question", "chosen", "alternatives", "rationale", "matters"),
    "feature": ("description", "requirements"),
    "nc": ("status", "detected_by", "corrected_by", "external_ref"),
}
DIR_KIND = {v: k for k, v in KIND_DIR.items()}


def dump_frontmatter(data: Mapping[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=100,
                          default_flow_style=False)


def ordered_frontmatter(kind: str, record_id: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Stable key order: id, title, the kind's fields, any others, status_note, links."""
    out: dict[str, Any] = {"id": record_id, "title": fields.get("title", "")}
    for key in FIELD_ORDER.get(kind, ()):
        if key in fields:
            out[key] = fields[key]
    for key, value in fields.items():
        if key not in out and key not in ("status_note", "links"):
            out[key] = value
    for key in ("status_note", "links"):
        if key in fields:
            out[key] = fields[key]
    return out


class Store:
    """Reads and writes record files. The index is loaded once and reused."""

    def __init__(self, paths: PlumbPaths) -> None:
        self.paths = paths
        self._index: dict[str, Record] | None = None
        self._problems: list[str] = []
        self._reserved: dict[str, list[str]] = {}  # IDs reserved ahead, per kind

    def invalidate(self) -> None:
        self._index = None
        self._problems = []

    def index(self) -> dict[str, Record]:
        if self._index is None:
            self._load()
        assert self._index is not None
        return self._index

    def problems(self) -> list[str]:
        """Errors found while loading: unparsable files, duplicates, misplaced records."""
        self.index()
        return list(self._problems)

    def _load(self) -> None:
        index: dict[str, Record] = {}
        problems: list[str] = []
        root = self.paths.root
        cached = _read_index_cache(self.paths.index_cache)
        fresh: dict[str, dict[str, object]] = {}
        now = time.time()
        for dirname, kind in sorted(DIR_KIND.items()):
            directory = self.paths.plumb / dirname
            if not directory.is_dir():
                continue
            prefix = directory.relative_to(root).as_posix()
            for name, stat in _md_files(directory):
                file = directory / name
                rel = f"{prefix}/{name}"
                stamp = [stat.st_size, stat.st_mtime_ns]
                entry = cached.get(rel)
                try:
                    record = _from_stamp(entry, stamp, rel)
                    if record is not None:  # size and mtime as cached: nothing read or hashed
                        fresh[rel] = entry  # type: ignore[assignment]
                    else:
                        record, kept = self._read(file, rel, entry)
                        if kept is not None:
                            if now - stat.st_mtime_ns / 1e9 > _RACY_S:
                                kept["stamp"] = stamp
                            fresh[rel] = kept
                except (RecordError, UnicodeDecodeError, OSError) as exc:
                    problems.append(f"{rel}: {exc}")
                    continue
                if record.kind != kind:
                    problems.append(f"{rel}: {record.id} is a {record.kind} record but sits in "
                                    f"{dirname}/ (expected {KIND_DIR[record.kind]}/)")
                if record.id in index:
                    problems.append(f"duplicate id {record.id}: {index[record.id].path} and "
                                    f"{rel}")
                    continue
                index[record.id] = record
        self._index = index
        self._problems = problems
        if fresh != cached:
            _write_index_cache(self.paths.index_cache, fresh)

    @staticmethod
    def _read(file: Any, rel: str, entry: object) -> tuple[Record, dict[str, object] | None]:
        """Read and parse one record file; the cache entry to keep (None when JSON cannot
        keep its frontmatter exactly). The entry's digest of the text spares the YAML."""
        text = file.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        hit = isinstance(entry, dict) and entry.get("digest") == digest
        data = entry.get("data") if hit else None  # type: ignore[union-attr]
        if not isinstance(data, dict):
            data = load_yaml(split_frontmatter(text)[0])
            hit = False
        record = parse_record(text, rel, data)
        if hit:  # validated when it was cached
            return record, {"digest": digest, "data": data, "body": record.body,
                            "hash": record.hash}
        if not _json_safe(data):
            return record, None
        return record, {"digest": digest, "data": data, "body": record.body,
                        "hash": record.hash}

    def next_id(self, kind: str) -> str:
        """A new ID of ``kind``, reserved through ``refs/plumb/ids`` (sp6 4.2): the one
        allocation function every record writer goes through."""
        queued = self._reserved.get(kind)
        if queued:
            return queued.pop(0)
        from plumb import ids

        return ids.reserve(self.paths, kind, local=self.index())[0]

    def prereserve(self, kind: str, count: int) -> None:
        """Reserve ``count`` IDs of ``kind`` in one compare-and-swap for the next
        ``next_id`` calls (a writer of several records reserves per prefix once, sp6 4.2).
        An ID reserved and never written leaves a gap; nothing relies on density."""
        if count <= 0:
            return
        from plumb import ids

        self._reserved.setdefault(kind, []).extend(
            ids.reserve(self.paths, kind, count, local=self.index()))

    def peek_id(self, kind: str) -> str:
        """The ID ``next_id`` would hand out, reserving nothing (previews, dry runs)."""
        from plumb import ids

        return ids.peek(self.paths, kind, local=self.index())

    def write_record(self, kind: str, fields: Mapping[str, Any], body: str = "",
                     *, record_id: str | None = None) -> Record:
        """Write a record file (new ID unless ``record_id``); returns the parsed record."""
        record_id = record_id or self.next_id(kind)
        existing = self.index().get(record_id)
        if existing is not None:
            path = self.paths.root / existing.path
        else:
            path = self.paths.plumb / KIND_DIR[kind] / f"{record_id}.md"
        data = ordered_frontmatter(kind, record_id, fields)
        text = "---\n" + dump_frontmatter(data) + "---\n" + body
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        self.invalidate()
        return self.index()[record_id]

    def set_links(self, record_id: str, links: list[dict[str, Any]]) -> Record:
        """Rewrite only the ``links`` field of a record; the body is kept byte for byte."""
        record = self.index()[record_id]
        path = self.paths.root / record.path
        text = path.read_bytes().decode("utf-8")
        _, body = split_frontmatter(text)
        from plumb.model import load_yaml

        data = load_yaml(split_frontmatter(text)[0])
        if links:
            data["links"] = links
        else:
            data.pop("links", None)
        new_text = "---\n" + dump_frontmatter(data) + "---\n" + body
        path.write_bytes(new_text.encode("utf-8"))
        self.invalidate()
        return self.index()[record_id]


# -- the index cache (spec 10): parsed frontmatter keyed by each file's content digest, so a
# warm hook never imports or runs YAML. Plain JSON in .plumb/cache/, rebuilt on any change.


def _md_files(directory: Any) -> list[tuple[str, os.stat_result]]:
    """The ``*.md`` files of a directory with their stat, in name order."""
    try:
        with os.scandir(directory) as scan:
            found = [(e.name, e.stat()) for e in scan
                     if e.name.endswith(".md") and e.is_file()]
    except OSError:
        return []
    return sorted(found, key=lambda item: os.path.normcase(item[0]))


def _from_stamp(entry: object, stamp: list[int], rel: str) -> Record | None:
    """The cached record when the entry's size and mtime are the file's, else None."""
    if not isinstance(entry, dict) or entry.get("stamp") != stamp:
        return None
    data, body, digest = entry.get("data"), entry.get("body"), entry.get("hash")
    if not isinstance(data, dict) or not isinstance(body, str) or not isinstance(digest, str):
        return None
    return record_from_parts(data, body, rel, digest)


def _json_safe(data: object) -> bool:
    """True when JSON keeps ``data`` exactly, types included (dates, for one, it does not)."""
    try:
        back = json.loads(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError):
        return False
    return back == data and _same_types(back, data)


def _same_types(a: Any, b: Any) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same_types(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same_types(x, y) for x, y in zip(a, b, strict=True))
    return True


def _read_index_cache(path: os.PathLike[str]) -> dict[str, object]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("v") != INDEX_CACHE_VERSION:
        return {}
    files = data.get("files")
    return files if isinstance(files, dict) else {}


def _write_index_cache(path: os.PathLike[str], files: Mapping[str, object]) -> None:
    from pathlib import Path

    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"v": INDEX_CACHE_VERSION, "files": files},
                                  ensure_ascii=False), encoding="utf-8", newline="\n")
        os.replace(tmp, target)
    except OSError:
        pass
