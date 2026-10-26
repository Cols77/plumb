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
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb.contracts import LogEntry, LogStream, MigrationReport
from plumb.normalize import canonical_json, sha256_bytes
from plumb.paths import PlumbPaths

SCHEMA = 1
LOCK_WAIT_S = 2.0
LOCK_STALE_S = 10.0
APPEND_BATCH_SIZE = 32  # bound each lock hold; every entry remains its own immutable file
PACK_VERSION = 1
# A cold read takes the entry files the pack cache misses from git's object store in one
# process once there are this many: one git process costs about as much as this many first
# opens of freshly written files (SR-073; _read_uncached).
GIT_BATCH_MIN = 16
GIT_BATCH_TIMEOUT_S = 10.0
SIBLING_MAX = 16  # other worktrees whose pack caches a cold read may consult
STREAMS: tuple[LogStream, ...] = ("events", "evidence")
STREAM_OF_KIND: dict[str, LogStream] = {"test-run": "evidence", "merge-evidence": "evidence"}

# SR-321: the kinds another clone needs are committed; the rest are written where they were
# but ignored by git (.gitignore lists exactly LOCAL_KINDS). A kind in neither set is a failing
# test (tests/logs/test_kinds.py).
SHARED_KINDS = frozenset({
    "approval", "prompt", "config", "calibration", "pre-intent", "question-answer", "premise",
    "judgment", "test-run", "mod-hello",
    "revocation", "browser-hello", "escalation-declined", "renumber", "import", "claims-ingest",
    "conflict-resolution", "waiver",
    "selfdebug-review",   # SR-326: the judge review of a self-fix, evidence of the landing
    "question-pushback", "question-ruling",   # SR-362: the agent sends back, the judge rules
    "answer-bound",       # SR-362: an answer given before its rewording, pointed at its keys
})
# SR-376: telemetry. The live entry files are ignored by git (.plumb/.gitignore); the landing
# moves every one older than the landing into the kind's tracked segment, liveness not consulted.
TELEMETRY_KINDS = frozenset({"judgment"})
LOCAL_KINDS = frozenset({
    "verdict", "trial", "card-press", "card-settled", "card-withdrawn", "gate", "read-entry",
    "job-note", "triage", "merge-evidence", "repin", "relink", "unlink", "eval-run", "jev-setup",
    "intent-gate", "intent-done", "card-unsettled",
})

_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_NAME_RE = re.compile(r"^(\d{8}T\d{6})\.(\d{6})Z-([0-9a-f]{8})\.json$")
_AT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")
_MIGRATED_MICROS = "000000"
# SR-287: a kind's archive segment, one canonical entry per line, appended by the landing's
# compaction. Hooks and session start read live entry files only (``LIVE_ONLY``, set by the
# hook runner); every other reader (validate, explain, calibration, judge jobs) reads through.
SEGMENT = "archive.jsonl"
LIVE_ONLY = False


class LogLockTimeout(RuntimeError):
    pass


class LogError(RuntimeError):
    """An entry the log refuses to write (the reason is a plain sentence)."""


# approvals written from the owner's words or a judge's verdict come from the worker (SR-210)
WORKER_ONLY_BY = frozenset({"owner-words", "auto-model", "auto-jev"})
# entry kinds only the worker writes
WORKER_ONLY_KINDS = frozenset({"pre-intent"})


def worker_token_problem(root: Path | str, session: str | None, by: str) -> str | None:
    """Why a ``by`` value (or a worker-only entry kind) may not be written here, or None.
    Those need ``PLUMB_WORKER`` equal to the ``token`` of the session's ``worker.lock``
    (tamper-evident, not tamper-proof). Other ``by`` values are not checked."""
    if by not in WORKER_ONLY_BY | WORKER_ONLY_KINDS:
        return None
    what = f"a {by} entry" if by in WORKER_ONLY_KINDS else f"a {by} approval"
    token = os.environ.get("PLUMB_WORKER")
    if not token:
        return f"{what} is written by the worker only (no worker token)"
    base = Path(root) / ".plumb" / "session"
    locks = [base / session / "worker.lock"] if session else sorted(base.glob("*/worker.lock"))
    for lock in locks:
        try:
            held = json.loads(lock.read_text(encoding="utf-8")).get("token")
        except (OSError, ValueError, AttributeError):
            continue
        if held and held == token:
            return None
    return f"{what} is written by the worker only (the token does not match)"


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


class _Scan:
    """One listing of a stream's entry files through its pack cache."""

    __slots__ = ("files", "fresh", "changed", "order", "segments")

    def __init__(self, files: dict[str, dict[str, Any]], fresh: dict[str, Any],
                 changed: bool, order: list[str] | None, segments: list[str]) -> None:
        self.files = files          # kind/file -> parsed entry (parsable files only)
        self.fresh = fresh          # the pack's file table for this listing
        self.changed = changed      # the table differs from the cached one
        self.order = order          # the cached read order, valid while nothing changed
        self.segments = segments    # the kinds with an archive segment (SR-287)


def _load_files(paths: PlumbPaths, stream: LogStream) -> dict[str, dict[str, Any]]:
    """Every parsable entry file of ``stream``, keyed ``kind/file``."""
    scan = _scan(paths, stream)
    if scan.changed:
        _write_pack(paths, stream, scan.fresh, None)
    return scan.files


def _write_pack(paths: PlumbPaths, stream: LogStream, fresh: dict[str, Any],
                order: list[str] | None) -> None:
    pack: dict[str, Any] = {"v": PACK_VERSION, "files": fresh}
    if order is not None:
        pack["order"] = order
    _write_json_atomic(paths.log_pack(stream), pack)


def _scan(paths: PlumbPaths, stream: LogStream) -> _Scan:
    """Every entry file of ``stream`` through the pack cache: a file whose size and mtime
    are unchanged is not read again; a vanished name is dropped."""
    pack = _read_json(paths.log_pack(stream))
    cached: dict[str, Any] = {}
    order: list[str] | None = None
    if isinstance(pack, dict) and pack.get("v") == PACK_VERSION \
            and isinstance(pack.get("files"), dict):
        cached = pack["files"]
        if isinstance(pack.get("order"), list):
            order = pack["order"]
    fresh: dict[str, Any] = {}
    out: dict[str, dict[str, Any]] = {}
    misses: list[tuple[str, str, int]] = []
    segments: list[str] = []
    for kind, directory in _kind_dirs(paths, stream):
        prefix = kind + "/"
        for item in _entry_files(directory):
            if item.name == SEGMENT:
                segments.append(kind)
                continue
            name = prefix + item.name
            try:
                st = item.stat()  # free on Windows: it comes with the directory listing
            except OSError:
                continue
            size, mtime = st.st_size, st.st_mtime_ns
            hit = cached.get(name)
            if type(hit) is list and len(hit) == 3 and hit[0] == size and hit[1] == mtime:
                fresh[name] = hit  # immutable entry, unchanged on disk: never read again
                if hit[2] is not None:
                    out[name] = hit[2]
            elif parse_name(item.name) is not None:
                fresh[name] = [size, mtime, None]
                misses.append((name, item.path, size))
    if misses:  # read in one place, git's object store first (_read_uncached)
        for name, raw in _read_uncached(paths, stream, misses).items():
            fresh[name][2] = raw
            if raw is not None:
                out[name] = raw
    changed = bool(misses) or len(fresh) != len(cached)
    return _Scan(out, fresh, changed, None if changed else order, segments)


def _parse_entry(data: bytes) -> dict[str, Any] | None:
    try:
        raw = json.loads(data)
    except ValueError:
        return None
    return raw if isinstance(raw, dict) else None


def _read_uncached(paths: PlumbPaths, stream: LogStream,
                   misses: list[tuple[str, str, int]]) -> dict[str, dict[str, Any] | None]:
    """The parsed content of the entry files the pack cache does not hold (``kind/file``,
    path, size on disk): the one place a reader reads an entry file.

    Guarantee (SR-073, the hook ceiling): a read in a worktree whose entry files git has just
    written (a ``git worktree add``, a ``git clone``, a merge, pull or checkout that brought
    many entries, a deleted or outdated pack cache) does not open those files one by one.
    The first open of a freshly written file pays the operating system's on-access scan
    (about 7 ms per file on Windows with Defender): seconds for a few hundred entries, more
    than a hook may spend. From ``GIT_BATCH_MIN`` misses on, an entry is taken, in order:

    1. from the pack cache of another worktree of the repository (entries are immutable and
       a name is unique, so the same name with the same size is the same entry; read-only,
       found through git's files, no process);
    2. from git's object store, in ONE ``git cat-file --batch`` by index path, when the
       blob's size matches the file on disk (with or without CRLF conversion);
    3. from the file itself (untracked new entries, a size mismatch, no git).

    An entry edited in place to the same size reads as the other copy; ``verify_chain``
    reads the files themselves and reports the edit."""
    out: dict[str, dict[str, Any] | None] = {}
    if len(misses) >= GIT_BATCH_MIN:
        out.update(_read_from_siblings(paths, stream, misses))
        rest = [miss for miss in misses if miss[0] not in out]
        if len(rest) >= GIT_BATCH_MIN:
            out.update(_read_from_git(paths, rest))
    for name, path, _size in misses:
        if name not in out:
            try:
                out[name] = _parse_entry(_read_file(path))
            except OSError:
                out[name] = None
    return out


def _worktree_roots(paths: PlumbPaths) -> list[Path]:
    """The plumb roots of the repository's other worktrees, read from git's own files (the
    ``.git`` file or directory, ``commondir``, ``worktrees/*/gitdir``); no process."""
    try:
        root = paths.root.resolve()
    except OSError:
        return []
    top = next((d for d in (root, *root.parents) if (d / ".git").exists()), None)
    if top is None:
        return []
    dotgit = top / ".git"
    try:
        if dotgit.is_file():
            text = dotgit.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return []
            gitdir = Path(text[len("gitdir:"):].strip())
            gitdir = gitdir if gitdir.is_absolute() else top / gitdir
            try:
                common = gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()
            except OSError:
                common = gitdir
        else:
            common = dotgit
        common = common.resolve()
    except OSError:
        return []
    tops: list[Path] = [common.parent] if common.name == ".git" else []
    try:
        with os.scandir(common / "worktrees") as it:
            for item in it:
                try:
                    pointer = Path(item.path, "gitdir").read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                tops.append(Path(pointer).parent)
    except OSError:
        pass
    rel = root.relative_to(top)
    own = os.path.normcase(str(top))
    return [t / rel for t in tops if os.path.normcase(str(t)) != own][:SIBLING_MAX]


def _read_from_siblings(paths: PlumbPaths, stream: LogStream,
                        misses: list[tuple[str, str, int]]) -> dict[str, dict[str, Any]]:
    """The misses another worktree's pack cache holds with the same size on disk."""
    out: dict[str, dict[str, Any]] = {}
    for other in _worktree_roots(paths):
        pack = _read_json(PlumbPaths(other).log_pack(stream))
        valid = isinstance(pack, dict) and pack.get("v") == PACK_VERSION
        files = pack.get("files") if valid else None
        if not isinstance(files, dict):
            continue
        for name, _path, size in misses:
            hit = files.get(name)
            if (name not in out and type(hit) is list and len(hit) == 3 and hit[0] == size
                    and isinstance(hit[2], dict)):
                out[name] = hit[2]
        if len(out) == len(misses):
            break
    return out


def _read_file(path: str) -> bytes:
    """One entry file read from disk (the direct path of ``_read_uncached``)."""
    return Path(path).read_bytes()


def _read_from_git(paths: PlumbPaths,
                   misses: list[tuple[str, str, int]]) -> dict[str, dict[str, Any] | None]:
    """The misses git's index holds with a blob the size of the file on disk; {} when git is
    unavailable, the root is not in a work tree, or anything goes wrong."""
    try:
        prefix = paths.log_dir.relative_to(paths.root).as_posix()
    except ValueError:
        return {}
    import subprocess  # lazy: the post-edit fast path imports this module (SR-287 EX-4)

    request = "".join(f":./{prefix}/{name}\n" for name, _, _ in misses).encode("ascii")
    try:
        result = subprocess.run(["git", "cat-file", "--batch"], cwd=paths.root, input=request,
                                capture_output=True, timeout=GIT_BATCH_TIMEOUT_S,
                                check=False)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    data = result.stdout
    out: dict[str, dict[str, Any] | None] = {}
    pos = 0
    for name, _path, disk_size in misses:
        end = data.find(b"\n", pos)
        if end < 0:
            break
        header = data[pos:end].split()
        pos = end + 1
        if len(header) != 3 or header[1] != b"blob" or not header[2].isdigit():
            continue  # "<request> missing": untracked or not in this index
        size = int(header[2])
        blob = data[pos:pos + size]
        pos += size + 1
        if len(blob) != size:
            break
        if disk_size in (size, size + blob.count(b"\n")):  # same file, maybe with CRLF
            out[name] = _parse_entry(blob)
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
    """A ``LogEntry`` built without the frozen dataclass's per-field ``__setattr__`` (a
    third of a warm read of 2000 entries); same class, same fields."""
    get = raw.get
    entry = object.__new__(LogEntry)
    entry.__dict__.update(stream=stream, kind=str(get("kind", "")), at=str(get("at", "")),
                          marker=str(get("marker", "none")), payload=get("payload") or {},
                          prev=get("prev"), digest=str(get("digest", "")), offset=offset,
                          name=name)
    return entry


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


def segment_lines(paths: PlumbPaths, stream: LogStream,
                  kinds: Iterable[str] | None = None) -> Iterator[tuple[str, int, bytes]]:
    """``(kind, line number, line)`` of every archive segment of ``stream`` (SR-287), or of
    ``kinds`` only (the kinds a listing found a segment in)."""
    wanted = None if kinds is None else set(kinds)
    for kind, directory in _kind_dirs(paths, stream):
        if wanted is not None and kind not in wanted:
            continue
        try:
            data = (Path(directory) / SEGMENT).read_bytes()
        except OSError:
            continue
        for number, line in enumerate(data.splitlines(), 1):
            if line.strip():
                yield kind, number, line


def _all_entries(paths: PlumbPaths, stream: LogStream,
                 since_offset: int = 0) -> list[LogEntry]:
    scan = _scan(paths, stream)
    try:
        legacy_present = paths.log_path(stream).stat().st_size > 0
    except OSError:
        legacy_present = False
    archived = ([] if LIVE_ONLY or not scan.segments
                else list(segment_lines(paths, stream, scan.segments)))
    legacy_present = legacy_present or bool(archived)  # the cached order is of live files only
    if scan.order is not None and not legacy_present:
        files = scan.files  # warm: nothing changed since the order was computed
        if all(name in files for name in scan.order):
            return [_to_entry(stream, files[name], -1, name) for name in scan.order]
    items: list[tuple[tuple[Any, ...], LogEntry]] = []
    seen: set[str] = set()
    for name, raw in scan.files.items():
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
    for kind, number, line in archived:
        raw = _parse_entry(line)
        if raw is None or str(raw.get("digest", "")) in seen:
            continue
        seen.add(str(raw.get("digest", "")))
        name = f"{kind}/{SEGMENT}:{number}"
        items.append(((str(raw.get("at", "")), 1, *_sort_name(name), 0),
                      _to_entry(stream, raw, -1, name)))
    result = _ordered(items)
    if not legacy_present:  # the order depends on the entry files alone: cache it
        _write_pack(paths, stream, scan.fresh, [e.name for e in result])
    elif scan.changed:
        _write_pack(paths, stream, scan.fresh, None)
    return result


# --------------------------------------------------------------------------- head


def _head(paths: PlumbPaths, stream: LogStream, data: dict[str, Any]) -> str | None:
    """The stream's latest digest: the head pointer, rebuilt by a scan when it is missing or
    names a file that no longer exists."""
    head = data.get(stream)
    if isinstance(head, dict):
        name = str(head.get("name", ""))
        digest = head.get("digest")
        if (isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                and "/" in name and (paths.log_dir / name).is_file()):
            return digest
    entries = _all_entries(paths, stream)
    if not entries:
        return None
    last = entries[-1]
    data[stream] = {"digest": last.digest, "name": last.name}
    return last.digest


# --------------------------------------------------------------------------- API


def append(paths: PlumbPaths, stream: LogStream, kind: str,
           payload: Mapping[str, Any]) -> LogEntry:
    """Write one entry as its own file under the per-worktree log lock; returns it."""
    return append_many(paths, stream, [(kind, payload)])[0]


def _validate_append(paths: PlumbPaths, stream: LogStream, kind: str,
                     payload: Mapping[str, Any]) -> None:
    if stream not in STREAMS:
        raise ValueError(f"unknown log stream: {stream}")
    if not _KIND_RE.match(kind):
        raise ValueError(f"not a log entry kind: {kind!r}")
    if stream_of(kind) != stream:
        raise ValueError(f"a {kind} entry belongs to the {stream_of(kind)} stream, "
                         f"not {stream}")
    by = kind if kind in WORKER_ONLY_KINDS else payload.get("by") if kind == "approval" else None
    if by in WORKER_ONLY_BY | WORKER_ONLY_KINDS:
        session = payload.get("session")
        problem = worker_token_problem(paths.root, session if isinstance(session, str)
                                       else None, str(by))
        if problem:
            raise LogError(problem)


def append_many(paths: PlumbPaths, stream: LogStream,
                entries: Sequence[tuple[str, Mapping[str, Any]]]) -> list[LogEntry]:
    """Append separate entries, with one lock and head publication per bounded chunk.

    Validate the whole request before writing. A failed chunk can persist a prefix: the
    head is removed BEFORE its first write, so even a process interruption forces the next
    writer to recover from the entry files instead of trusting an obsolete pointer.
    """
    if stream not in STREAMS:
        raise ValueError(f"unknown log stream: {stream}")
    pending = [(kind, dict(payload)) for kind, payload in entries]
    for kind, payload in pending:
        _validate_append(paths, stream, kind, payload)
        canonical_json(payload)  # serialization errors must also precede persistence
    result: list[LogEntry] = []
    for offset in range(0, len(pending), APPEND_BATCH_SIZE):
        with _Lock(paths):
            data = _read_json(paths.log_head)
            if not isinstance(data, dict):
                data = {}
                prev = None
                for other in STREAMS:
                    recovered = _head(paths, other, data)
                    if other == stream:
                        prev = recovered
            else:
                prev = _head(paths, stream, data)
            # An inability to invalidate must abort before persisting any entry.
            paths.log_head.unlink(missing_ok=True)
            for kind, payload in pending[offset:offset + APPEND_BATCH_SIZE]:
                now = time.time()
                entry: dict[str, Any] = {
                    "v": SCHEMA, "kind": kind,
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "marker": current_marker(), "payload": payload, "prev": prev}
                entry["digest"] = entry_digest(entry)
                file_name = _write_new(paths, paths.log_kind_dir(kind),
                                       canonical_json(entry) + b"\n",
                                       (_new_name(now) for _ in range(100)))
                name = f"{kind}/{file_name}"
                prev = entry["digest"]
                data[stream] = {"digest": prev, "name": name}
                result.append(_to_entry(stream, entry, -1, name))
            _write_json_atomic(paths.log_head, data)
    return result


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
    """A cheap token that changes whenever an entry of ``stream`` is added, removed or
    rewritten (per kind directory: its mtime, the number of entries and the last name; the
    legacy file's size and mtime), for derived caches. One listing per kind, no file read."""
    parts: list[str] = []
    try:
        st = os.stat(paths.log_path(stream))
        parts.append(f"legacy:{st.st_size}:{st.st_mtime_ns}")
    except OSError:
        pass
    for kind, directory in _kind_dirs(paths, stream):
        names = [item.name for item in _entry_files(directory)]
        try:
            mtime = os.stat(directory).st_mtime_ns
        except OSError:
            mtime = 0
        parts.append(f"{kind}:{mtime}:{len(names)}:{max(names, default='')}")
    return ";".join(parts) or "-"


def verify_chain(paths: PlumbPaths, stream: LogStream) -> list[str]:
    """Problems in a stream, naming the file or the legacy line: unparsable files and lines,
    wrong digests (an edited entry or legacy line), a file name that does not parse or a migrated name whose
    suffix does not match its digest. A ``prev`` naming no entry here is no problem (SR-322)."""
    problems: list[str] = []
    files: list[tuple[str, dict[str, Any]]] = []
    digests: set[str] = set()
    for kind, directory in _kind_dirs(paths, stream):
        for item in sorted(_entry_files(directory), key=lambda e: e.name):
            name = f"{kind}/{item.name}"
            parsed = parse_name(item.name)
            if item.name == SEGMENT:
                continue
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
    for kind, number, line in segment_lines(paths, stream):
        name = f"{kind}/{SEGMENT} line {number}"
        raw = _parse_entry(line)
        if raw is None:
            problems.append(f"{name}: not a JSON object")
            continue
        if raw.get("digest") != entry_digest(raw):
            problems.append(f"{name}: digest {str(raw.get('digest'))[:19]} does not match the "
                            "entry (modified entry)")
        if raw.get("kind") != kind:
            problems.append(f"{name}: kind {raw.get('kind')!r} does not match its directory")
        if isinstance(raw.get("digest"), str):
            digests.add(raw["digest"])
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
    # SR-322: a ``prev`` naming no entry here is not a problem (another session's, branch's or
    # a local kind's entry), for entry files and legacy lines alike; the merge check refuses
    # deletions.
    for number, raw, file_name in legacy:
        assert raw is not None
        if raw.get("digest") != entry_digest(raw):
            problems.append(f"{file_name} line {number}: digest does not match the entry "
                            "(modified line)")
    return problems


def archive(paths: PlumbPaths, names: Iterable[str]) -> list[str]:
    """Move entry files (``kind/file``) into their kind's archive segment (SR-287): each
    entry appended once, unchanged (its digest and prev kept), then its file removed. Returns
    the paths, relative to the root, of the segments written and the files removed."""
    by_kind: dict[str, list[str]] = {}
    for name in sorted(names, key=_sort_name):
        kind, _, file_name = name.partition("/")
        by_kind.setdefault(kind, []).append(file_name)
    changed: list[str] = []
    with _Lock(paths):
        for kind, file_names in sorted(by_kind.items()):
            directory = paths.log_kind_dir(kind)
            segment = directory / SEGMENT
            try:
                have = {str(json.loads(line).get("digest")) for line in
                        segment.read_bytes().splitlines() if line.strip()}
            except (OSError, ValueError, AttributeError):
                have = set()
            lines: list[bytes] = []
            moved: list[str] = []
            for file_name in file_names:
                raw = _read_json(directory / file_name)
                if not isinstance(raw, dict) or raw.get("digest") != entry_digest(raw):
                    continue  # an unreadable or edited entry stays where validate reports it
                moved.append(file_name)
                if str(raw.get("digest")) not in have:
                    lines.append(canonical_json(raw) + b"\n")
                    have.add(str(raw.get("digest")))
            if lines:
                with open(segment, "ab") as handle:
                    handle.write(b"".join(lines))
                    handle.flush()
                    os.fsync(handle.fileno())
                changed.append(segment.relative_to(paths.root).as_posix())
            for file_name in moved:  # removed only once the segment holds it
                try:
                    os.remove(directory / file_name)
                    changed.append((directory / file_name).relative_to(paths.root).as_posix())
                except OSError:
                    pass
    return changed


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
            heads: dict[str, Any] = {}
            for stream in STREAMS:
                _head(paths, stream, heads)
            _write_json_atomic(paths.log_head, heads)
    remaining = lines if dry_run else legacy_count(paths)
    return MigrationReport(lines=lines, written=tuple(written), skipped=skipped,
                           refused=tuple(refused), truncated=tuple(truncated),
                           remaining=remaining, dry_run=dry_run)


def tracked_names(root: Path) -> set[str]:
    """The committed entry files (``kind/file``) of the log, as ``git ls-files`` lists them."""
    import subprocess

    prefix = ".plumb/log/"
    out = subprocess.run(["git", "ls-files", "--", prefix], cwd=root, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", check=True).stdout
    return {p[len(prefix):] for p in out.split("\n") if p.startswith(prefix)}


def shared_uncommitted(root: Path) -> list[str]:
    """SR-329: the uncommitted entries of shared log kinds in ``root``, whichever session wrote
    them (local kinds are ignored by git, so they never appear)."""
    import subprocess

    out = subprocess.run(["git", "ls-files", "-o", "--exclude-standard", "-z", "--", ".plumb/log"],
                         cwd=root, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", check=True).stdout
    return sorted(p for p in out.split(chr(0)) if p.count("/") >= 3
                  and p.split("/")[2] in SHARED_KINDS)


def untracked_telemetry_out(root: Path, paths: Iterable[str]) -> list[str]:
    """``paths`` without the telemetry entry files git does not track (ignored: naming them
    would fail ``git add`` and ``git commit``)."""
    paths = list(paths)

    def loose(p: str) -> bool:
        parts = p.split("/")
        return (len(parts) == 4 and p.startswith(".plumb/log/") and parts[2] in TELEMETRY_KINDS
                and parts[3] != SEGMENT)

    if not any(loose(p) for p in paths):
        return paths
    known = {".plumb/log/" + n for n in tracked_names(root)}
    return [p for p in paths if p in known or not loose(p)]


def stage(root: Path, changed: Iterable[str]) -> None:
    """``git add -A`` of the paths ``archive`` returned (segments written, files removed).
    Nothing else is staged."""
    # a local kind's entry is never staged (SR-321, SR-287 EX-16), nor an ignored telemetry file
    changed = [c for c in changed if not (c.startswith(".plumb/log/")
                                          and c.split("/")[2] in LOCAL_KINDS)]
    changed = untracked_telemetry_out(root, changed)
    if not changed:
        return
    import subprocess

    done = subprocess.run(["git", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"],
                          cwd=root, input="\0".join(changed), env={**os.environ,
                          "GIT_LITERAL_PATHSPECS": "1"}, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode:
        raise RuntimeError(f"git add: {done.stderr.strip()[:200]}")


def untracked_own(tree: Path, status_line: str) -> bool:
    """Is this ``git status --porcelain`` line an untracked log or cache file of ``tree``:
    plumb's own output, not uncommitted work?"""
    own = PlumbPaths(tree)
    skip = tuple(p.relative_to(tree).as_posix() + "/" for p in (own.log_dir, own.cache))
    return status_line.startswith("?? ") and status_line[3:].startswith(skip)
