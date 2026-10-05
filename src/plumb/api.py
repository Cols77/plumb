"""``open_core``: the CoreAPI every other lane builds on (spec 12.1, 12.2)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

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

    # -- configuration and caches
    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = load_config(self.root)
        return self._config

    def events(self) -> list[LogEntry]:
        """Every entry of ``events.jsonl``, cached for this instance."""
        if self._events is None:
            self._events = list(_log.read(self.paths, "events"))
        return self._events

    # -- CoreAPI
    def index(self) -> Mapping[str, Record]:
        return self.store.index()

    def status(self, ids: Iterable[str] | None = None) -> Mapping[str, RecordStatus]:
        from plumb.confirm import statuses

        return statuses(self, ids)

    def link_states(self, ids: Iterable[str] | None = None) -> Sequence[LinkState]:
        from plumb.links import link_states

        return link_states(self, ids)

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
        entry = _log.append(self.paths, stream, kind, payload)
        if stream == "events":
            self._events = None
        return entry

    def log_read(self, stream: LogStream, kinds: Iterable[str] | None = None,
                 since_offset: int = 0) -> Iterator[LogEntry]:
        return _log.read(self.paths, stream, kinds, since_offset)


def open_core(root: Path) -> Core:
    return Core(Path(root))
