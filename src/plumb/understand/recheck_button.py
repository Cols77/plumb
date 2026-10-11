"""Re-check of an ``approval`` with ``by: owner, via: button`` (sp7-realign-sp8 C6): the offer
exists in that session, was drawn before the entry, names this record at this hash, the key
digest is the one in ``mod.json``, and the marker is ``none``. Until the press lands (slice 4)
the check refuses every such entry, so a button approval confirms nothing yet."""

from __future__ import annotations

from typing import Any

from plumb.contracts import LogEntry

NOT_YET = ("a button approval cannot be checked yet (the press is not built), so it confirms "
           "nothing")


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why ``entry`` fails its re-check: always, for now."""
    return NOT_YET
