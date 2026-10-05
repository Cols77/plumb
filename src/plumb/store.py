"""The record store: ``.plumb/<kind dir>/*.md`` (spec 4.2, 5.3, 5.8)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from typing import Any

from plumb.contracts import KIND_DIR, KIND_PREFIX, Record
from plumb.model import RecordError, load_yaml, parse_record, split_frontmatter
from plumb.paths import PlumbPaths

INDEX_CACHE_VERSION = 1

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
        for dirname, kind in sorted(DIR_KIND.items()):
            directory = self.paths.plumb / dirname
            if not directory.is_dir():
                continue
            for file in sorted(directory.glob("*.md")):
                rel = file.relative_to(root).as_posix()
                try:
                    text = file.read_text(encoding="utf-8")
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    entry = cached.get(rel)
                    hit = isinstance(entry, dict) and entry.get("digest") == digest
                    data = entry.get("data") if hit else None  # type: ignore[union-attr]
                    if not isinstance(data, dict):
                        data = load_yaml(split_frontmatter(text)[0])
                    record = parse_record(text, rel, data)
                except (RecordError, UnicodeDecodeError, OSError) as exc:
                    problems.append(f"{rel}: {exc}")
                    continue
                if _json_safe(data):
                    fresh[rel] = {"digest": digest, "data": data}
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

    def next_id(self, kind: str) -> str:
        prefix = KIND_PREFIX[kind]
        width = 4 if kind == "nc" else 3
        pattern = re.compile(rf"^{prefix}-(\d+)$")
        numbers = [int(m.group(1)) for rid in self.index() if (m := pattern.match(rid))]
        return f"{prefix}-{(max(numbers) + 1 if numbers else 1):0{width}d}"

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
