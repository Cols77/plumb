"""Frozen parts (SR-380): the paths under ``freeze:`` in ``.iaso/config.yaml`` take no part in
drift, the brief, the merge hold or the evidence a requirement waits on, and a record marked
``frozen: true`` counts nowhere (``query.retired_ids``). A part that names a host (``codex``,
``hermes``) wakes when that host works on iaso: its session marker is set."""

from __future__ import annotations

from typing import Any

HOSTS = ("codex", "hermes")


def is_frozen(config: Any, path: str | None) -> bool:
    """Whether ``path`` (a repository-relative file or ``file::test``) is in a frozen part that
    is asleep: one naming no host always, one naming a host unless that host is the agent."""
    if not path or not config.freeze:
        return False
    from iaso.log import current_marker

    rel = path.partition("::")[0].replace("\\", "/")
    for part in config.freeze:
        part = str(part).replace("\\", "/").rstrip("/")
        if rel == part or rel.startswith(part + "/"):
            if next((h for h in HOSTS if h in part), None) != current_marker():
                return True
    return False
