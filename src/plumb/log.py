"""Append-only, hash-chained JSONL logs (spec 5.7, 12.4).

One JSON object per line: ``{v, kind, at, marker, payload, prev, digest}``. ``digest`` is the
sha256 of the canonical JSON of every other field; ``prev`` is the digest of the previous line
(null for the first line of a chain). Branches merged with ``merge=union`` fork the chain,
which is accepted; a modified, deleted or reordered committed line is reported.

The chain is tamper-evident, not tamper-proof: an agent can forge an entry before it is
committed. Every entry records the session marker in force.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from plumb.contracts import LogEntry, LogStream
from plumb.normalize import canonical_json, sha256_bytes, utc_now
from plumb.paths import PlumbPaths

SCHEMA = 1
LOCK_WAIT_S = 2.0
LOCK_STALE_S = 10.0


class LogLockTimeout(RuntimeError):
    pass


def current_marker() -> str:
    return os.environ.get("PLUMB_AGENT_SESSION") or "none"


def entry_digest(entry: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json({k: v for k, v in entry.items() if k != "digest"}))


class _Lock:
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


def _last_line(path: os.PathLike[str] | str) -> tuple[bytes, bool]:
    """The last non-empty line of a file and whether the file ends with a newline."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size == 0:
                return b"", True
            block = 4096
            data = b""
            pos = size
            while pos > 0:
                step = min(block, pos)
                pos -= step
                handle.seek(pos)
                data = handle.read(step) + data
                stripped = data.rstrip(b"\r\n")
                if b"\n" in stripped or pos == 0:
                    break
            ends_newline = data.endswith(b"\n")
            stripped = data.rstrip(b"\r\n")
            return stripped.rsplit(b"\n", 1)[-1], ends_newline
    except FileNotFoundError:
        return b"", True


def append(paths: PlumbPaths, stream: LogStream, kind: str,
           payload: Mapping[str, Any]) -> LogEntry:
    """Append one entry under the log lock with a single write; returns it."""
    path = paths.log_path(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _Lock(paths):
        last, ends_newline = _last_line(path)
        prev = None
        if last.strip():
            try:
                prev = json.loads(last).get("digest")
            except ValueError:
                prev = None
        entry: dict[str, Any] = {"v": SCHEMA, "kind": kind, "at": utc_now(),
                                 "marker": current_marker(), "payload": dict(payload),
                                 "prev": prev}
        entry["digest"] = entry_digest(entry)
        line = canonical_json(entry) + b"\n"
        if not ends_newline:
            line = b"\n" + line
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0))
        try:
            offset = os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
    if not ends_newline:
        offset += 1
    return _to_entry(stream, entry, offset)


def _to_entry(stream: LogStream, raw: Mapping[str, Any], offset: int) -> LogEntry:
    return LogEntry(stream=stream, kind=str(raw.get("kind", "")), at=str(raw.get("at", "")),
                    marker=str(raw.get("marker", "none")), payload=raw.get("payload") or {},
                    prev=raw.get("prev"), digest=str(raw.get("digest", "")), offset=offset)


def _raw_lines(paths: PlumbPaths, stream: LogStream,
               since_offset: int = 0) -> Iterator[tuple[int, bytes]]:
    path = paths.log_path(stream)
    try:
        handle = open(path, "rb")
    except FileNotFoundError:
        return
    with handle:
        handle.seek(since_offset)
        offset = since_offset
        for line in handle:
            yield offset, line
            offset += len(line)


def read(paths: PlumbPaths, stream: LogStream, kinds: Iterable[str] | None = None,
         since_offset: int = 0) -> Iterator[LogEntry]:
    """Entries from ``since_offset`` on, optionally only of ``kinds``. Bad lines are skipped
    (``verify_chain`` reports them)."""
    wanted = set(kinds) if kinds is not None else None
    for offset, line in _raw_lines(paths, stream, since_offset):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        if wanted is not None and raw.get("kind") not in wanted:
            continue
        yield _to_entry(stream, raw, offset)


def verify_chain(paths: PlumbPaths, stream: LogStream) -> list[str]:
    """Problems in a stream: unparsable lines, wrong digests, ``prev`` not an earlier line."""
    problems: list[str] = []
    seen: set[str] = set()
    name = paths.log_path(stream).name
    lineno = 0
    for _, line in _raw_lines(paths, stream):
        lineno += 1
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            problems.append(f"{name} line {lineno}: not valid JSON")
            continue
        if not isinstance(raw, dict):
            problems.append(f"{name} line {lineno}: not a JSON object")
            continue
        digest = raw.get("digest")
        if digest != entry_digest(raw):
            problems.append(f"{name} line {lineno}: digest does not match the entry "
                            "(modified line)")
        prev = raw.get("prev")
        if prev is not None and prev not in seen:
            problems.append(f"{name} line {lineno}: prev {str(prev)[:19]} is not an earlier "
                            "line (deleted or reordered entry)")
        if isinstance(digest, str):
            seen.add(digest)
    return problems
