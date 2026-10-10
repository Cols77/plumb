"""Drift caught at the edit that causes it (SR-111).

``.plumb/cache/linkmap.json`` maps every pinned link end to the link, so the edit hook can
name the links an edit made stale from the hash cache alone: no YAML and no record index
(standard library plus ``plumb.hashing``). ``ensure_linkmap`` rewrites it only when the
record index digest changed. A missing or unreadable map says nothing; the stop hook is the
backstop.

The turn baseline, the hold-open and the stale cards (HA4, HA5) live below the link map.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from plumb.api import Core

CACHE_REL = ".plumb/cache/linkmap.json"
VERSION = 1
DERIVING = frozenset({"derives_from", "decides", "upstream"})
MAX_NOTICES = 5

NOTICE = ("plumb: {record}'s link to {path} is stale: the file changed; rerun its tests and "
          "repin, reword {record}, or bring it to the owner as a card")
DERIVED = "{source} {verb} {target}, which was reworded: check that it still agrees"
_VERBS = {"derives_from": "derives from", "decides": "decides", "upstream": "rests on"}


class End(NamedTuple):
    """One pinned link end in a file: the record, the link id and the pinned target hash."""

    record: str
    link: str
    pin: str
    symbol: str | None = None
    test: str | None = None


class StaleLink(NamedTuple):
    record: str
    link: str
    path: str
    now: str | None   # the end's current hash; None when it no longer exists
    pin: str


def cache_path(root: Path | str) -> Path:
    return Path(root) / CACHE_REL


def _link_key(link: Any) -> list[Any]:
    target = link.target
    pin = link.pin
    return [link.kind, target.record, target.path, target.symbol, target.test, link.example,
            None if pin is None else [pin.source, pin.target]]


def index_digest(index: Mapping[str, Any]) -> str:
    """What the link map rests on: every record's hash, file and links with their pins."""
    items = [[r.id, r.hash, r.path, [_link_key(link) for link in r.links]]
             for r in (index[i] for i in sorted(index))]
    return hashlib.sha256(json.dumps(items, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clean(raw: str) -> str | None:
    from plumb.hashing import clean_rel_path

    return clean_rel_path(raw)


def build_linkmap(index: Mapping[str, Any]) -> dict[str, Any]:
    from plumb.hashing import target_path

    ends: dict[str, list[list[Any]]] = {}
    derived: dict[str, list[list[Any]]] = {}
    records: dict[str, str] = {}
    for record_id in sorted(index):
        record = index[record_id]
        records[record.path] = record.id
        for link in record.links:
            if link.pin is None:
                continue
            target = link.target
            if target.record is not None:
                if link.kind in DERIVING:
                    derived.setdefault(target.record, []).append(
                        [record.id, link.id, link.pin.target, link.kind])
                continue
            raw = target_path(target)
            rel = _clean(raw) if raw else None
            if rel is None:
                continue
            ends.setdefault(rel, []).append(
                [record.id, link.id, link.pin.target, target.symbol, target.test])
    return {"v": VERSION, "digest": index_digest(index), "ends": ends, "derived": derived,
            "records": records}


def load_linkmap(root: Path | str) -> dict[str, Any] | None:
    try:
        data = json.loads(cache_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("v") != VERSION:
        return None
    if not all(isinstance(data.get(k), dict) for k in ("ends", "derived", "records")):
        return None
    return data


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def ensure_linkmap(core: Core, *, force: bool = False) -> bool:
    """Rewrite the link map when the record index digest changed; True when it was written."""
    index = core.index()
    digest = index_digest(index)
    current = load_linkmap(core.root)
    if not force and current is not None and current.get("digest") == digest:
        try:  # the records were rewritten without a change the map rests on: it is current
            os.utime(cache_path(core.root))
        except OSError:
            pass
        return False
    data = build_linkmap(index)
    try:
        _write_atomic(cache_path(core.root), json.dumps(data, separators=(",", ":")))
    except OSError:
        return False
    return True


RECORD_DIRS = ("intents", "requirements", "decisions", "features", "ncs")


def linkmap_outdated(root: Path | str) -> bool:
    """True when a record file is newer than the link map (a record or link was written
    since): a stat of the record files, no parsing. False without a map."""
    try:
        stamp = cache_path(root).stat().st_mtime_ns
    except OSError:
        return False
    for name in RECORD_DIRS:
        try:
            scan = os.scandir(Path(root) / ".plumb" / name)
        except OSError:
            continue
        with scan:
            for entry in scan:
                try:
                    if entry.name.endswith(".md") and entry.stat().st_mtime_ns > stamp:
                        return True
                except OSError:
                    continue
    return False


def links_touching(root: Path | str, rel: str) -> list[End]:
    """The pinned link ends inside the repository file ``rel`` (empty without a map)."""
    data = load_linkmap(root)
    key = _clean(rel)
    if data is None or key is None:
        return []
    out = []
    for item in data["ends"].get(key, ()):
        if isinstance(item, list) and len(item) == 5:
            out.append(End(*item))
    return out


def record_for_path(root: Path | str, rel: str) -> str | None:
    """The record whose file is ``rel`` (a direct edit of a record), or None."""
    data = load_linkmap(root)
    key = _clean(rel)
    if data is None or key is None:
        return None
    found = data["records"].get(key)
    return found if isinstance(found, str) else None


def current_hash(root: Path | str, rel: str, end: End) -> str | None:
    from plumb.contracts import Target
    from plumb.hashing import hash_target

    if end.test:
        target = Target(test=end.test)
    elif end.symbol:
        target = Target(path=rel, symbol=end.symbol)
    else:
        target = Target(path=rel)
    return hash_target(Path(root), {}, target)


def stale_after_edit(root: Path | str, rel: str) -> list[StaleLink]:
    """The links whose end inside ``rel`` no longer matches its pin."""
    out = []
    for end in links_touching(root, rel):
        now = current_hash(root, rel, end)
        if now != end.pin:
            out.append(StaleLink(end.record, end.link, rel, now, end.pin))
    return out


def notice(item: StaleLink) -> str:
    return NOTICE.format(record=item.record, path=item.path)


def notices(items: Sequence[StaleLink], limit: int = MAX_NOTICES) -> list[str]:
    """One line per stale link, at most ``limit``, then ``+N more``."""
    lines = [notice(item) for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"plumb: +{len(items) - limit} more")
    return lines


def derived_stale(core: Core, ids: Iterable[str]) -> list[tuple[str, str, str, str]]:
    """``(source, target, link id, kind)`` of every link from a record to one of ``ids``
    whose pin no longer matches that record (it was reworded since the pin)."""
    wanted = set(ids)
    index = core.index()
    out = []
    for record in index.values():
        for link in record.links:
            target = link.target.record
            if (target in wanted and target in index and link.kind in DERIVING
                    and link.pin is not None and link.pin.target != index[target].hash):
                out.append((record.id, target, link.id, link.kind))
    return sorted(out)


def derived_line(source: str, target: str, kind: str) -> str:
    return DERIVED.format(source=source, verb=_VERBS.get(kind, "relies on"), target=target)


def derived_lines(core: Core, ids: Iterable[str]) -> list[str]:
    """``SR-032 derives from INT-016, which was reworded: check that it still agrees``."""
    return [derived_line(source, target, kind)
            for source, target, _link, kind in derived_stale(core, ids)]


# --------------------------------------------------------------------------- the turn baseline


def session_path(root: Path | str, session: str) -> Path:
    return Path(root) / ".plumb" / "session" / session


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_baseline(root: Path | str, session: str) -> dict[str, dict[str, list[str]]]:
    """The links stale at the turn start: ``{link id: {"pin": [source, target], "now":
    [source, target]}}`` (empty without a baseline)."""
    data = _read_json(session_path(root, session) / "stale_baseline.json")
    links = data.get("links") if isinstance(data, dict) else None
    return links if isinstance(links, dict) else {}


def was_told(root: Path | str, session: str, key: str, state: str) -> bool:
    data = _read_json(session_path(root, session) / "stale_told.json")
    return isinstance(data, dict) and data.get(key) == state


def mark_told(root: Path | str, session: str, items: Mapping[str, str]) -> None:
    """Remember what the edit check said (one line per link state, said once)."""
    path = session_path(root, session) / "stale_told.json"
    data = _read_json(path)
    data = dict(data) if isinstance(data, dict) else {}
    data.update(items)
    try:
        _write_atomic(path, json.dumps(data))
    except OSError:
        pass
