"""``KINDS``: job kind -> the module implementing ``JobKind`` (imported on first use)."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

KIND_MODULES: dict[str, str] = {"read": "plumb.understand.read",
                                "judge": "plumb.understand.judge",
                                "clarify": "plumb.understand.clarify"}


class _Kinds:
    def __getitem__(self, kind: str) -> Any:
        return importlib.import_module(KIND_MODULES[kind])

    def __iter__(self) -> Iterator[str]:
        return iter(KIND_MODULES)

    def __len__(self) -> int:
        return len(KIND_MODULES)

    def __contains__(self, kind: object) -> bool:
        return kind in KIND_MODULES

    def keys(self) -> Any:
        return KIND_MODULES.keys()

    def get(self, kind: str, default: Any = None) -> Any:
        return self[kind] if kind in KIND_MODULES else default


KINDS = _Kinds()
