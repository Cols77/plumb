"""The reader's threshold (SR-101 EX-14)."""

from __future__ import annotations

from typing import Any


def reader_threshold(core: Any) -> float:
    return float(core.config.understand.reader_threshold_start)
