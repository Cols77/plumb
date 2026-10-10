"""Dispatchers (ENGINE): ``configured(core)`` returns exactly one. Stub: no model."""

from __future__ import annotations

from typing import Any

from plumb.contracts import Dispatcher, NoModel


def configured(core: Any) -> Dispatcher:
    raise NoModel("no model configured")
