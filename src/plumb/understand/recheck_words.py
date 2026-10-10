"""Re-check of ``by: owner-words`` approvals (READ). Stub: a hand-written entry of this kind
is never accepted."""

from __future__ import annotations

from typing import Any

from plumb.contracts import LogEntry
from plumb.present.owner_text import NOT_AVAILABLE


def problem(entry: LogEntry, core: Any) -> str | None:
    return NOT_AVAILABLE
