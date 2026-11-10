"""Re-check of the approval and revocation kinds the worker writes: dispatches by ``by`` to
``recheck_words`` (owner-words) and ``typed`` (undone)."""

from __future__ import annotations

import importlib
from typing import Any

from iaso.contracts import LogEntry

BY_MODULE = {"owner-words": "iaso.understand.recheck_words",
             "undone": "iaso.understand.typed",
             "auto-model": "iaso.understand.recheck_model"}


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why ``entry`` fails its re-check, or None. Other ``by`` values are not this module's."""
    by = str(entry.payload.get("by"))
    module_name = BY_MODULE.get(by)
    if module_name is None:
        return None
    return importlib.import_module(module_name).problem(entry, core)
