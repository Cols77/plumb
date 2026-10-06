"""Append-only, hash-chained logs: one file per entry (spec 5.7, 12.4; SP6 6, SR-073, SR-074).

Every entry is its own file ``.plumb/log/<kind>/<stamp>-<suffix>.json`` holding the canonical
JSON of ``{v, kind, at, marker, payload, prev, digest}`` plus a newline. ``digest`` is the
sha256 of the canonical JSON of every other field; ``prev`` is the digest of the stream's
previous entry (null for the first). Two streams exist, as before: ``evidence`` for
``test-run`` and ``merge-evidence``, ``events`` for every other kind (``STREAM_OF_KIND``).

Two worktrees or branches that append create different files, so git never sees two changes
to one path and merges under ``.plumb/log/`` cannot conflict; a merge forks the chain, which
is accepted while every ``prev`` resolves. A modified entry, a deleted entry that a later
``prev`` names, and an unparsable file are reported.

During the transition readers also accept the legacy ``events.jsonl`` and ``evidence.jsonl``
lines, deduplicated by digest; ``migrate`` moves them into entry files without changing a
digest (SR-074).

The chain is tamper-evident, not tamper-proof: an agent can forge an entry before it is
committed. Every entry records the session marker in force.
"""

from __future__ import annotations

import heapq
import json
import os
import re
import time
import uuid
from collections.abc import Collection, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from plumb.contracts import LogEntry, LogStream, MigrationReport
from plumb.normalize import canonical_json, sha256_bytes
from plumb.paths import PlumbPaths

SCHEMA = 1
LOCK_WAIT_S = 2.0
LOCK_STALE_S = 10.0
PACK_VERSION = 1
STREAMS: tuple[LogStream, ...] = ("events", "evidence")
STREAM_OF_KIND: dict[str, LogStream] = {"test-run": "evidence", "merge-evidence": "evidence"}

_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_NAME_RE = re.compile(r"^(\d{8}T\d{6})\.(\d{6})Z-([0-9a-f]{8})\.json$")
_AT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")
_MIGRATED_MICROS = "000000"


class LogLockTimeout(RuntimeError):
    pass


def current_marker() -> str:
    return os.environ.get("PLUMB_AGENT_SESSION") or "none"


def entry_digest(entry: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json({k: v for k, v in entry.items() if k != "digest"}))


def stream_of(kind: str) -> LogStream:
    """The stream a kind belongs to: ``evidence`` for test runs and merge evidence."""
    return STREAM_OF_KIND.get(kind, "events")


# --------------------------------------------------------------------------- names


def parse_name(file_name: str) -> tuple[str, str, str] | None:
    """``(stamp seconds, microseconds, suffix)`` of an entry file name, else None."""
    match = _NAME_RE.match(file_name)
    return (match.group(1), match.group(2), match.group(3)) if match else None


def is_migrated_name(file_name: str) -> bool:
    parsed = parse_name(file_name)
    return parsed is not None and parsed[1] == _MIGRATED_MICROS


def migrated_name(raw: Mapping[str, Any]) -> str | None:
    """The file name a legacy line migrates to: its own ``at`` with ``.000000`` and characters
    8 to 15 of its digest's hex, so one line always gets one name. None if ``at`` or the
    digest does not have the expected shape."""
    match = _AT_RE.match(str(raw.get("at", "")))
    digest = str(raw.get("digest", ""))
    hexpart = digest.split(":", 1)[-1]
    if match is None or len(hexpart) < 16 or not re.fullmatch(r"[0-9a-f]+", hexpart):
        return None
    y, mo, d, h, mi, s = match.groups()
    return f"{y}{mo}{d}T{h}{mi}{s}.{_MIGRATED_MICROS}Z-{hexpart[8:16]}.json"


def _new_name(now: float) -> str:
    micros = int(round((now % 1) * 1_000_000)) % 1_000_000 or 1  # .000000 marks a migration
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now))
    return f"{stamp}.{micros:06d}Z-{uuid.uuid4().hex[:8]}.json"


def _sort_name(name: str) -> tuple[str, str]:
    """``kind/file`` sorts by the file name (its stamp) first."""
    kind, _, file_name = name.partition("/")
    return file_name, kind


# --------------------------------------------------------------------------- lock


class _Lock:
    """The per-worktree log lock (``.plumb/cache/log.lock``); nothing spans worktrees."""

    def __init__(self, paths: PlumbPaths) -> None:
        self.path = paths.lock

    def __enter__(self) -> _Lock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_S:
                        os.remove(self.path)
                        continue
                except OSError:
                    continue
                if time.monotonic() > deadline:
                    raise LogLockTimeout(f"log lock busy: {self.path}") from None
                time.sleep(0.005)
            except PermissionError:  # Windows: the file is being deleted by another holder
                if time.monotonic() > deadline:
                    raise LogLockTimeout(f"log lock busy: {self.path}") from None
                time.sleep(0.005)

    def __exit__(self, *exc: object) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass


# --------------------------------------------------------------------------- small files


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json_atomic(path: Path, data: Any) -> None:
    """Best effort: a cache that cannot be written is rebuilt next time."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        try:
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
    except OSError:
        pass


def _write_new(paths: PlumbPaths, directory: Path, data: bytes,
               names: Iterable[str]) -> str:
    """Write ``data`` under the first of ``names`` that does not exist: a temporary file in
    the gitignored cache, then ``os.link`` to the final name (fails if it exists: no
    replace), fsync. Returns the name written; FileExistsError when every name exists."""
    directory.mkdir(parents=True, exist_ok=True)
    paths.cache.mkdir(parents=True, exist_ok=True)
    tmp = paths.cache / f".log-{uuid.uuid4().hex}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        for name in names:
            target = directory / name
            try:
                os.link(tmp, target)
                return name
            except FileExistsError:
                continue
            except OSError:
                # no hard links on this filesystem: an exclusive create is no-replace too
                try:
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, "O_BINARY", 0))
                except FileExistsError:
                    continue
                try:
                    os.write(fd, data)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                return name
        raise FileExistsError(f"no free entry name in {directory}")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- scanning


def _kind_dirs(paths: PlumbPaths, stream: LogStream) -> list[tuple[str, str]]:
    """``(kind, directory path)`` of every kind directory of ``stream``."""
    out: list[tuple[str, str]] = []
    try:
        with os.scandir(paths.log_dir) as it:
            for item in it:
                if (item.is_dir() and _KIND_RE.match(item.name)
                        and stream_of(item.name) == stream):
                    out.append((item.name, item.path))
    except OSError:
        return []
    return sorted(out)


def _entry_files(directory: str) -> Iterator[os.DirEntry[str]]:
    try:
        with os.scandir(directory) as it:
            for item in it:
                if item.is_file():
                    yield item
    except OSError:
        return


def _load_files(paths: PlumbPaths, stream: LogStream) -> dict[str, dict[str, Any]]:
    """Every parsable entry file of ``stream``, keyed ``kind/file``, through the pack cache:
    a file whose size and mtime are unchanged is not read again; a vanished name is dropped."""
    pack_path = paths.log_pack(stream)
    pack = _read_json(pack_path)
    cached: dict[str, Any] = {}
    if isinstance(pack, dict) and pack.get("v") == PACK_VERSION \
            and isinstance(pack.get("files"), dict):
        cached = pack["files"]
    fresh: dict[str, Any] = {}
    changed = False
    out: dict[str, dict[str, Any]] = {}
    for kind, directory in _kind_dirs(paths, stream):
        for item in _entry_files(directory):
            if parse_name(item.name) is None:
                continue
            name = f"{kind}/{item.name}"
            try:
                st = item.stat()
            except OSError:
                continue
            key = [st.st_size, st.st_mtime_ns]
            hit = cached.get(name)
            if isinstance(hit, list) and len(hit) == 3 and hit[:2] == key:
                raw = hit[2]
            else:
                changed = True
                try:
                    raw = json.loads(Path(item.path).read_bytes())
                except (OSError, ValueError):
                    raw = None
                if not isinstance(raw, dict):
                    raw = None
            fresh[name] = [key[0], key[1], raw]
            if raw is not None:
                out[name] = raw
    if changed or len(fresh) != len(cached):
        _write_json_atomic(pack_path, {"v": PACK_VERSION, "files": fresh})
    return out


def _legacy_lines(paths: PlumbPaths, stream: LogStream,
                  since_offset: int = 0) -> Iterator[tuple[int, int, bytes]]:
    """``(line number, byte offset, line)`` of the legacy JSONL file of ``stream``."""
    path = paths.log_path(stream)
    try:
        handle = open(path, "rb")
    except FileNotFoundError:
        return
    with handle:
        offset = 0
        number = 0
        for line in handle:
            number += 1
            if offset >= since_offset:
                yield number, offset, line
            offset += len(line)


def _to_entry(stream: LogStream, raw: Mapping[str, Any], offset: int, name: str) -> LogEntry:
    return LogEntry(stream=stream, kind=str(raw.get("kind", "")), at=str(raw.get("at", "")),
                    marker=str(raw.get("marker", "none")), payload=raw.get("payload") or {},
                    prev=raw.get("prev"), digest=str(raw.get("digest", "")), offset=offset,
                    name=name)


def _ordered(items: list[tuple[tuple[Any, ...], LogEntry]]) -> list[LogEntry]:
    """By ``at``, then the chain (an entry after the entry its ``prev`` names), then the
    name: a heap-ordered topological walk, so a skewed clock never puts an entry before the
    entry it chains to."""
    by_digest = {entry.digest: i for i, (_, entry) in enumerate(items)}
    children: dict[int, list[int]] = {}
    ready: list[tuple[tuple[Any, ...], int]] = []
    for i, (key, entry) in enumerate(items):
        parent = by_digest.get(entry.prev) if entry.prev else None
        if parent is None or parent == i:
            ready.append((key, i))
        else:
            children.setdefault(parent, []).append(i)
    heapq.heapify(ready)
    out: list[LogEntry] = []
    done: set[int] = set()
    while ready:
        _, i = heapq.heappop(ready)
        done.add(i)
        out.append(items[i][1])
        for child in children.get(i, ()):
            heapq.heappush(ready, (items[child][0], child))
    if len(out) < len(items):  # a cycle of forged digests: the rest by key
        out.extend(entry for _, entry in sorted(
            (item for j, item in enumerate(items) if j not in done), key=lambda t: t[0]))
    return out


def _all_entries(paths: PlumbPaths, stream: LogStream,
                 since_offset: int = 0) -> list[LogEntry]:
    items: list[tuple[tuple[Any, ...], LogEntry]] = []
    seen: set[str] = set()
    for name, raw in _load_files(paths, stream).items():
        digest = str(raw.get("digest", ""))
        if digest in seen:
            continue
        seen.add(digest)
        entry = _to_entry(stream, raw, -1, name)
        items.append(((entry.at, 1, *_sort_name(name), 0), entry))
    legacy = paths.log_path(stream).name
    for number, offset, line in _legacy_lines(paths, stream, since_offset):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        digest = str(raw.get("digest", ""))
        if digest in seen:  # a migrated line and its file are one entry
            continue
        seen.add(digest)
        entry = _to_entry(stream, raw, offset, f"{legacy}:{number}")
        items.append(((entry.at, 0, "", "", offset), entry))
    return _ordered(items)


# --------------------------------------------------------------------------- head


def _head(paths: PlumbPaths, stream: LogStream) -> str | None:
    """The stream's latest digest: the head pointer, rebuilt by a scan when it is missing or
    names a file that no longer exists."""
    data = _read_json(paths.log_head)
    head = data.get(stream) if isinstance(data, dict) else None
    if isinstance(head, dict):
        name = str(head.get("name", ""))
        if "/" in name and (paths.log_dir / name).is_file():
            digest = head.get("digest")
            return str(digest) if digest else None
    entries = _all_entries(paths, stream)
    if not entries:
        return None
    last = entries[-1]
    _set_head(paths, stream, last.digest, last.name)
    return last.digest


def _set_head(paths: PlumbPaths, stream: LogStream, digest: str, name: str) -> None:
    data = _read_json(paths.log_head)
    if not isinstance(data, dict):
        data = {}
    data[stream] = {"digest": digest, "name": name}
    _write_json_atomic(paths.log_head, data)


# --------------------------------------------------------------------------- API


def append(paths: PlumbPaths, stream: LogStream, kind: str,
           payload: Mapping[str, Any]) -> LogEntry:
    """Write one entry as its own file under the per-worktree log lock; returns it."""
    if stream not in STREAMS:
        raise ValueError(f"unknown log stream: {stream}")
    if not _KIND_RE.match(kind):
        raise ValueError(f"not a log entry kind: {kind!r}")
    if stream_of(kind) != stream:
        raise ValueError(f"a {kind} entry belongs to the {stream_of(kind)} stream, "
                         f"not {stream}")
    directory = paths.log_kind_dir(kind)
    with _Lock(paths):
        prev = _head(paths, stream)
        now = time.time()
        entry: dict[str, Any] = {"v": SCHEMA, "kind": kind,
                                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                                 "marker": current_marker(), "payload": dict(payload),
                                 "prev": prev}
        entry["digest"] = entry_digest(entry)
        file_name = _write_new(paths, directory, canonical_json(entry) + b"\n",
                               (_new_name(now) for _ in range(100)))  # a clash: new suffix
        name = f"{kind}/{file_name}"
        _set_head(paths, stream, entry["digest"], name)
    return _to_entry(stream, entry, -1, name)


def read(paths: PlumbPaths, stream: LogStream, kinds: Iterable[str] | None = None,
         since_offset: int = 0, *, since: Collection[str] | None = None) -> Iterator[LogEntry]:
    """Entries of both formats, deduplicated by digest, in order (by ``at``, then the chain,
    then the name), optionally only of ``kinds``. ``since`` skips the names already applied;
    ``since_offset`` skips legacy lines before that byte offset. Bad files and lines are
    skipped (``verify_chain`` reports them)."""
    wanted = set(kinds) if kinds is not None else None
    skip = set(since) if since else None
    for entry in _all_entries(paths, stream, since_offset):
        if wanted is not None and entry.kind not in wanted:
            continue
        if skip is not None and entry.name in skip:
            continue
        yield entry


def valid_entries(paths: PlumbPaths, stream: LogStream) -> dict[str, str]:
    """``kind/file`` -> digest of every entry file whose content matches its digest."""
    return {name: str(raw.get("digest")) for name, raw in _load_files(paths, stream).items()
            if raw.get("digest") == entry_digest(raw)}


def legacy_count(paths: PlumbPaths) -> int:
    """Lines still in the legacy JSONL files (both streams)."""
    count = 0
    for stream in STREAMS:
        try:
            if paths.log_path(stream).stat().st_size == 0:
                continue
        except OSError:
            continue
        count += sum(1 for _, _, line in _legacy_lines(paths, stream) if line.strip())
    return count


def stream_stamp(paths: PlumbPaths, stream: LogStream) -> str:
    """A cheap token that changes whenever an entry of ``stream`` is added or removed (the
    kind directories' and the legacy file's size and mtime): for derived caches."""
    parts: list[str] = []
    for target in [paths.log_path(stream), *(Path(d) for _, d in _kind_dirs(paths, stream))]:
        try:
            st = os.stat(target)
        except OSError:
            continue
        parts.append(f"{target.name}:{st.st_size}:{st.st_mtime_ns}")
    return ";".join(parts) or "-"


def verify_chain(paths: PlumbPaths, stream: LogStream) -> list[str]:
    """Problems in a stream, naming the file or the legacy line: unparsable files and lines,
    wrong digests (an edited entry), a ``prev`` that resolves to no entry (a deleted entry a
    later one names), a file name that does not parse or a migrated name whose suffix does
    not match its digest, and a legacy line whose ``prev`` is not an earlier line or entry."""
    problems: list[str] = []
    files: list[tuple[str, dict[str, Any]]] = []
    digests: set[str] = set()
    for kind, directory in _kind_dirs(paths, stream):
        for item in sorted(_entry_files(directory), key=lambda e: e.name):
            name = f"{kind}/{item.name}"
            parsed = parse_name(item.name)
            if parsed is None:
                problems.append(f"{name}: not an entry file name (<stamp>-<suffix>.json)")
                continue
            try:
                raw = json.loads(Path(item.path).read_bytes())
            except (OSError, ValueError):
                problems.append(f"{name}: not valid JSON")
                continue
            if not isinstance(raw, dict):
                problems.append(f"{name}: not a JSON object")
                continue
            digest = raw.get("digest")
            if digest != entry_digest(raw):
                problems.append(f"{name}: digest does not match the entry (modified entry)")
            elif parsed[1] == _MIGRATED_MICROS and \
                    str(digest).split(":", 1)[-1][8:16] != parsed[2]:
                problems.append(f"{name}: migrated name does not match the entry's digest")
            if raw.get("kind") != kind:
                problems.append(f"{name}: kind {raw.get('kind')!r} does not match its "
                                "directory")
            if isinstance(digest, str):
                digests.add(digest)
            files.append((name, raw))
    legacy: list[tuple[int, dict[str, Any] | None, str]] = []
    legacy_name = paths.log_path(stream).name
    for number, _, line in _legacy_lines(paths, stream):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            problems.append(f"{legacy_name} line {number}: not valid JSON")
            continue
        if not isinstance(raw, dict):
            problems.append(f"{legacy_name} line {number}: not a JSON object")
            continue
        legacy.append((number, raw, legacy_name))
    legacy_digests = {str(r.get("digest")) for _, r, _ in legacy if r is not None}
    for name, raw in files:
        prev = raw.get("prev")
        if prev is not None and prev not in digests and prev not in legacy_digests:
            problems.append(f"{name}: prev {str(prev)[:19]} names no entry of the stream "
                            "(deleted entry)")
    earlier: set[str] = set()
    for number, raw, file_name in legacy:
        assert raw is not None
        digest = raw.get("digest")
        if digest != entry_digest(raw):
            problems.append(f"{file_name} line {number}: digest does not match the entry "
                            "(modified line)")
        prev = raw.get("prev")
        if prev is not None and prev not in earlier and prev not in digests:
            problems.append(f"{file_name} line {number}: prev {str(prev)[:19]} is not an "
                            "earlier line (deleted or reordered entry)")
        if isinstance(digest, str):
            earlier.add(digest)
    return problems


# --------------------------------------------------------------------------- migration


def migrate(paths: PlumbPaths, *, dry_run: bool) -> MigrationReport:
    """Move every legacy JSONL line into its own entry file with exactly the line's fields
    (SR-074). A bad line (not JSON, not an object, a digest that does not match, an unusable
    kind or ``at``) refuses the whole run and writes nothing. Existing names are skipped (a
    name is a function of the digest). The legacy files are emptied, not deleted, once every
    line is present as a file; the head pointer and pack caches are rebuilt."""
    planned: list[tuple[LogStream, str, str, dict[str, Any]]] = []
    refused: list[str] = []
    lines = 0
    for stream in STREAMS:
        legacy_name = paths.log_path(stream).name
        for number, _, line in _legacy_lines(paths, stream):
            if not line.strip():
                continue
            lines += 1
            where = f"{legacy_name} line {number}"
            try:
                raw = json.loads(line)
            except ValueError:
                refused.append(f"{where}: not valid JSON")
                continue
            if not isinstance(raw, dict):
                refused.append(f"{where}: not a JSON object")
                continue
            if raw.get("digest") != entry_digest(raw):
                refused.append(f"{where}: digest does not match the entry (modified line)")
                continue
            kind = str(raw.get("kind", ""))
            if not _KIND_RE.match(kind) or stream_of(kind) != stream:
                refused.append(f"{where}: kind {kind!r} cannot be an entry of the {stream} "
                               "stream")
                continue
            file_name = migrated_name(raw)
            if file_name is None:
                refused.append(f"{where}: its time {raw.get('at')!r} cannot name an entry")
                continue
            planned.append((stream, kind, file_name, raw))
    if refused:
        return MigrationReport(lines=lines, refused=tuple(refused),
                               remaining=lines, dry_run=dry_run)
    written: list[str] = []
    skipped = 0
    seen: set[str] = set()
    with _Lock(paths):
        for _stream, kind, file_name, raw in planned:
            name = f"{kind}/{file_name}"
            target = paths.log_kind_dir(kind) / file_name
            if name in seen:  # the same line twice (a union merge): one entry
                skipped += 1
                continue
            seen.add(name)
            if target.exists():
                existing = _read_json(target)
                same = isinstance(existing, dict) and existing.get("digest") == raw.get("digest")
                if not same:
                    refused.append(f"{name}: exists with other content; its line stays")
                skipped += 1
                continue
            written.append(name)
            if not dry_run:
                try:
                    _write_new(paths, paths.log_kind_dir(kind), canonical_json(raw) + b"\n",
                               [file_name])
                except FileExistsError:
                    written.pop()
                    skipped += 1
        truncated: list[str] = []
        if not dry_run and not refused:
            for stream in STREAMS:
                path = paths.log_path(stream)
                try:
                    if path.stat().st_size == 0:
                        continue
                except OSError:
                    continue
                with open(path, "wb"):
                    pass
                truncated.append(path.name)
        if not dry_run:
            for stream in STREAMS:
                try:
                    os.remove(paths.log_pack(stream))
                except OSError:
                    pass
            try:
                os.remove(paths.log_head)
            except OSError:
                pass
            for stream in STREAMS:
                _head(paths, stream)
    remaining = lines if dry_run else legacy_count(paths)
    return MigrationReport(lines=lines, written=tuple(written), skipped=skipped,
                           refused=tuple(refused), truncated=tuple(truncated),
                           remaining=remaining, dry_run=dry_run)
