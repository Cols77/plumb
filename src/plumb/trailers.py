"""``SR:`` commit trailer parsing (spec 5.9).

Extracted from pi-agent-factory's ``coherence/register/claims.py`` (``parse_sr_trailer``,
``invalid_ids``). Only a line starting with ``SR:`` counts; a mention in prose is no claim.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from plumb.contracts import ID_RE

TRAILER_KEY = "SR"
_TRAILER_RE = re.compile(rf"^{TRAILER_KEY}:[ \t]*(.+?)[ \t\r]*$", re.MULTILINE)
_ID_RE = re.compile(ID_RE)


def parse_sr_trailer(message: str) -> tuple[str, ...]:
    """IDs from every ``SR:`` trailer line, in declaration order, deduplicated."""
    ids: list[str] = []
    for raw in _TRAILER_RE.findall(message):
        for chunk in raw.split(","):
            token = chunk.strip()
            if token and token not in ids:
                ids.append(token)
    return tuple(ids)


def invalid_ids(ids: Sequence[str]) -> tuple[str, ...]:
    """The IDs that are not shaped like a plumb record ID."""
    return tuple(i for i in ids if not _ID_RE.match(i))
