"""The backlog pass (JUDGE, SR-107). J1 form: placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plumb.contracts import Applied, CardState


@dataclass
class After:
    cards: list[CardState] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def after_job(core: Any, job: Any, **_: Any) -> After:
    return After()


def effect(**_: Any) -> Applied | None:
    return None
