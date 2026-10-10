"""Settling (JUDGE, SR-106). J1 form: nothing settles yet; every supported record waits."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from plumb.contracts import CardState, Job


@dataclass(frozen=True)
class Supported:
    """A record the judge found supported, at the version judged."""

    record: Any
    score: float
    premise: Mapping[str, Any]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class Waiting:
    """A supported record that is not settled: ``reason`` is why it is asked on its own
    ('' when it simply waits for a trial batch)."""

    item: Supported
    reason: str = ""


@dataclass
class Routed:
    entries: list[Mapping[str, Any]] = field(default_factory=list)
    cards: list[CardState] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    waiting: list[Waiting] = field(default_factory=list)


def route(core: Any, job: Job, supported: list[Supported], *, model: str = "") -> Routed:
    return Routed(waiting=[Waiting(s) for s in supported])
