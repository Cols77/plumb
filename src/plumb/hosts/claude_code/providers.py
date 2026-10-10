"""Lazy access to the other lanes through their factory functions (spec 12.2).

A provider whose module is missing from this build, or that fails to open, degrades to
``None``; the hook then prints ``plumb: <part> unavailable`` and continues. Tests pass fakes
instead of the ``LAZY`` default.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

LAZY: Any = object()


def verify_api(core: Any, given: Any = LAZY) -> Any:
    """``plumb.verify.open_verify(core, hook=True)``, or None when VERIFY is unavailable.

    Hook mode: a hook never builds a cold test map inline; it gets the unknown-coverage
    sample and the pending flag instead, and the map is built outside its budget (R5)."""
    if given is not LAZY:
        return given
    try:
        from plumb.verify import open_verify
    except ImportError:
        return None
    try:
        return open_verify(core, hook=True)
    except Exception:  # noqa: BLE001 - a failing lane degrades, never breaks a hook
        return None


def judgment_backend(core: Any, given: Any = LAZY) -> Any:
    """``plumb.judgment.get_backend(core, hook=True)``, or None when the judgment modules are
    missing. A judge that is not configured or has no key raises ``JudgmentUnavailable``
    (INT-029): the caller reports it; no rule-based judge stands in."""
    if given is not LAZY:
        return given
    try:
        from plumb.judgment import JudgmentUnavailable, get_backend
    except ImportError:
        return None
    try:
        return get_backend(core, hook=True)
    except JudgmentUnavailable:
        raise
    except Exception:  # noqa: BLE001
        return None


def unjudged_fn(given: Any = LAZY) -> Callable[[Any, Iterable[str] | None], tuple[str, ...]] | None:
    """``plumb.judgment.fidelity.unjudged``, or None when unavailable."""
    if given is not LAZY:
        return given
    try:
        from plumb.judgment.fidelity import unjudged
    except ImportError:
        return None
    return unjudged
