"""Re-check of ``by: settled`` approvals and ``by: undone`` revocations (JUDGE). Stub: a
hand-written entry of these kinds is never accepted."""

from __future__ import annotations

from typing import Any

from plumb.contracts import LogEntry
from plumb.present.owner_text import NOT_AVAILABLE


def problem(entry: LogEntry, core: Any) -> str | None:
    return NOT_AVAILABLE
