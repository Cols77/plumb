"""``open_core``: the CoreAPI every other lane builds on (spec 12.1, 12.2)."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from plumb import hashing as _hashing
from plumb import log as _log
from plumb.config import Config, load_config
from plumb.contracts import (
    Link,
    LinkKind,
    LinkState,
    LogEntry,
    LogStream,
    Record,
    RecordKind,
    RecordStatus,
    Target,
)
from plumb.hashing import hash_target as _hash_target
from plumb.paths import PlumbPaths
from plumb.store import Store


class Core:
    """CoreAPI over one repository. Reads are cached per instance; writes invalidate."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.paths = PlumbPaths(self.root)
        self.store = Store(self.paths)
        self._config: Config | None = None
        self._events: list[LogEntry] | None = None
        # inside one hook process (hashing.stat_cached) statuses and link states are computed
        # once: kept while the record index, the events and the link-end hashes are the same
        self._ends_memo: tuple[Any, dict[str, set[str]]] | None = None
        self._link_basis: tuple[Any, int] | None = None
        self._link_memo: dict[str, list[LinkState]] = {}
        self._status_basis: tuple[Any, Any, int] | None = None
        self._status_memo: dict[str, RecordStatus] | None = None

    def _links_memo_valid(self) -> bool:
        """True when link states may be kept (a hook process); drops them once the record
        index or the link-end hashes moved."""
        if not _hashing.ends_memo_active():
            self._link_basis = None
            self._link_memo = {}
            return False
        basis = (self.store.index(), _hashing.ends_generation())
        old = self._link_basis
        if old is None or old[0] is not basis[0] or old[1] != basis[1]:
            self._link_basis = basis
            self._link_memo = {}
        return True

    def _status_memo_valid(self) -> bool:
        """The same for statuses, which also rest on the events."""
        if not self._links_memo_valid():
            self._status_basis = None
            self._status_memo = None
            return False
        basis = (self.store.index(), self.events(), _hashing.ends_generation())
        old = self._status_basis
        if (old is None or old[0] is not basis[0] or old[1] is not basis[1]
                or old[2] != basis[2]):
            self._status_basis = basis
            self._status_memo = None
        return True

    # -- configuration and caches
    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = load_config(self.root)
        return self._config

    def events(self) -> list[LogEntry]:
        """Every entry of the events stream (both formats), cached for this instance."""
        if self._events is None:
            own = list(_log.read(self.paths, "events"))
            held = {e.digest for e in own}      # DEC-116: the owner's words other checkouts hold
            more = [e for e in _log.other_checkouts(self.paths) if e.digest not in held]
            self._events = sorted(own + more, key=lambda e: e.at) if more else own
        return self._events

    # -- CoreAPI
    def index(self) -> Mapping[str, Record]:
        return self.store.index()

    def status(self, ids: Iterable[str] | None = None) -> Mapping[str, RecordStatus]:
        from plumb.confirm import statuses

        if not self._status_memo_valid():
            return statuses(self, ids)
        if self._status_memo is None:
            if ids is not None:
                return statuses(self, ids)
            self._status_memo = statuses(self, None)
        if ids is None:
            return dict(self._status_memo)
        return {i: self._status_memo[i] for i in ids if i in self._status_memo}

    def link_states(self, ids: Iterable[str] | None = None) -> Sequence[LinkState]:
        from plumb.links import link_states

        if not self._links_memo_valid():
            return link_states(self, ids)
        index = self.index()
        selected = list(index) if ids is None else [i for i in ids if i in index]
        missing = [i for i in selected if i not in self._link_memo]
        if missing:
            computed = link_states(self, missing)
            for record_id in missing:
                self._link_memo[record_id] = []
            for state in computed:
                self._link_memo[state.link.source].append(state)
        return [state for i in selected for state in self._link_memo[i]]

    def records_for_paths(self, paths: Iterable[str]) -> Mapping[str, tuple[str, ...]]:
        from plumb.links import records_for_paths

        return records_for_paths(self, paths)

    def relevant(self, text: str, limit: int = 5) -> Sequence[tuple[str, float]]:
        from plumb.query import relevant

        return relevant(self, text, limit)

    def brief_lines(self, max_lines: int = 30) -> list[str]:
        from plumb.query import brief_lines

        return brief_lines(self, max_lines)

    def hash_target(self, target: Target) -> str | None:
        return _hash_target(self.root, self.index(), target)

    def write_record(self, kind: RecordKind, fields: Mapping[str, Any], body: str = "",
                     *, record_id: str | None = None) -> Record:
        return self.store.write_record(kind, fields, body, record_id=record_id)

    def add_link(self, source: str, kind: LinkKind, target: Target,
                 example: str | None = None) -> Link:
        from plumb.links import add_link

        return add_link(self, source, kind, target, example)

    def log_append(self, stream: LogStream, kind: str,
                   payload: Mapping[str, Any]) -> LogEntry:
        try:
            return _log.append(self.paths, stream, kind, payload)
        finally:
            if stream == "events":
                self._events = None

    def log_append_many(self, stream: LogStream,
                        entries: Sequence[tuple[str, Mapping[str, Any]]]) -> list[LogEntry]:
        try:
            return _log.append_many(self.paths, stream, entries)
        finally:
            # A failed batch can have persisted a prefix, which subsequent jobs must see.
            if stream == "events":
                self._events = None

    def log_read(self, stream: LogStream, kinds: Iterable[str] | None = None,
                 since_offset: int = 0, *,
                 since: Collection[str] | None = None) -> Iterator[LogEntry]:
        return _log.read(self.paths, stream, kinds, since_offset, since=since)


def open_core(root: Path) -> Core:
    return Core(Path(root))
