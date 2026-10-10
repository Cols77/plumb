"""A command of the understanding layer. Stub: not available in this build."""

from __future__ import annotations

import sys

from plumb.present.owner_text import NOT_AVAILABLE


def run(command: str, argv: list[str]) -> int:
    print(f"plumb: {command}: {NOT_AVAILABLE}", file=sys.stderr)
    return 2
