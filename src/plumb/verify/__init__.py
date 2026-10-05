"""Covering-test verification (spec 7): the test map, selection, runs, evidence, policy.

``open_verify(core)`` is the lane's factory function (spec 12.2). Kept import-light: the
heavy modules load only when a method needs them.
"""

from __future__ import annotations

from typing import Any


def open_verify(core: Any) -> Any:
    """The VerifyAPI over ``core`` (spec 12.1, 12.2)."""
    from plumb.verify.api import Verify

    return Verify(core)


__all__ = ["open_verify"]
