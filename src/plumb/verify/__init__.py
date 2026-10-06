"""Covering-test verification (spec 7): the test map, selection, runs, evidence, policy.

``open_verify(core)`` is the lane's factory function (spec 12.2). Kept import-light: the
heavy modules load only when a method needs them.

Inside a hook (``HOOK_PROCESS``, set by the hook runner, or ``hook=True``) the VerifyAPI
never builds a cold test map inline: a map that would take longer than a hook may spend is
built outside the hook, and the hook falls back to the unknown-coverage sample plus the
``full verification pending`` flag (R5; ``Verify.select``).
"""

from __future__ import annotations

from typing import Any

HOOK_PROCESS = False  # True while a hook runs in this process (hookio.run_hook)


def open_verify(core: Any, *, hook: bool | None = None) -> Any:
    """The VerifyAPI over ``core`` (spec 12.1, 12.2); in hook mode inside a hook."""
    from plumb.verify.api import Verify

    return Verify(core, hook=HOOK_PROCESS if hook is None else hook)


__all__ = ["HOOK_PROCESS", "open_verify"]
