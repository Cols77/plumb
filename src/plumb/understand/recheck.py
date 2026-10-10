"""Re-check of the approval and revocation kinds the worker writes: dispatches by ``by`` to
``recheck_words`` (owner-words) and ``recheck_settled`` (settled, undone)."""

from __future__ import annotations

import importlib
from typing import Any

from plumb.contracts import LogEntry

BY_MODULE = {"owner-words": "plumb.understand.recheck_words",
             "settled": "plumb.understand.recheck_settled",
             "undone": "plumb.understand.recheck_settled"}


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why ``entry`` fails its re-check, or None. Other ``by`` values are not this module's."""
    module_name = BY_MODULE.get(str(entry.payload.get("by")))
    if module_name is None:
        return None
    return importlib.import_module(module_name).problem(entry, core)

