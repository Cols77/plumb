"""Cross-worktree awareness and intent in flight (sp6 9, rulings R10.4 and R17).

Awareness instead of locks: each worktree publishes what it is changing into its own cache,
reads the others' read-only from git's files, and shares the intent it has in flight through
the ``refs/iaso/claims`` register, so a contradiction is caught when intent is captured, not
at merge. Nothing here takes a lock, holds a lease, or refuses anything.

The interface the hooks, the status card and ``iaso status`` use (sp6 12) is loaded lazily,
so the post-edit hook's ``note_edit`` imports only ``iaso.awareness.publish``.
"""

from __future__ import annotations

from typing import Any

_API = {"brief_entries": "lines", "brief_lines": "lines", "card_text": "lines",
        "delta_lines": "lines", "snapshot_fields": "lines", "status_section": "lines",
        "status_data": "lines",
        "note_edit": "publish", "publish": "publish", "overlaps": "scan"}

__all__ = sorted(_API)


def __getattr__(name: str) -> Any:
    module = _API.get(name)
    if module is None:
        raise AttributeError(f"module 'iaso.awareness' has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(f"iaso.awareness.{module}"), name)
