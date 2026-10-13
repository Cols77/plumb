"""The model-backed understanding layer (docs/plans/sp8-plan.md): jobs a worker runs, the
cards the owner answers, the gate and the progress. Phase C holds the contracts and stubs;
each lane fills its own modules. Standard library only at import."""

from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


def stub(func: _F) -> _F:
    """Mark a phase C2 stub (``fn.__stub__ = True``); the lane that writes the real code
    removes the marker, and the test stand-ins then step aside."""
    func.__stub__ = True  # type: ignore[attr-defined]
    return func
