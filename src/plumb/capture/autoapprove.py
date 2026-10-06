"""Narrow auto-approval, opt-in and off by default (R8 B, R13 Q3; sp2 8.2, SR-041)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plumb.api import Core


def gate(core: Core, ids: Sequence[str], *, prompt_digest: str | None,
         backend: Any = None) -> list[str]:
    """IDs approved ``by: auto-jev``; empty unless auto-approval is effective."""
    return []
