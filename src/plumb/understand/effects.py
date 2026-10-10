"""The registry of what an answered card does (plan 3.2 item 4). READ applies the answers and
calls the handler of the card's kind; JUDGE registers trial, backlog, beyond, contradicts;
SHOW registers clarify, couldnt_check; READ registers show_first."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

Handler = Callable[..., Any]
HANDLERS: dict[str, Handler] = {}


def register(card_kind: str, handler: Handler) -> None:
    HANDLERS[card_kind] = handler


# card kinds only a typed command or a button can answer; a prose answer changes nothing
NO_EFFECT = frozenset({"settle_offer", "settled_item"})


def handler_for(card_kind: str) -> Handler | None:
    """Import every kind module (they register their handlers at import; an import error is
    raised, not hidden), then look up."""
    from plumb.understand.kinds import KIND_MODULES

    for module in list(KIND_MODULES.values()):
        importlib.import_module(module)
    return HANDLERS.get(card_kind)
