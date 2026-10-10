"""The gate that holds a build until the owner answers (SHOW). Stub: never closed."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_closed(root: Path, session: str) -> bool:
    return False


def problems(core: Any) -> list[str]:
    return []
