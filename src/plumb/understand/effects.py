"""The registry of what an answered card does (plan 3.2 item 4). READ applies the answers and
calls the handler of the card's kind; JUDGE registers trial, backlog, beyond, contradicts;
SHOW registers clarify, couldnt_check; READ registers show_first."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Handler = Callable[..., Any]
HANDLERS: dict[str, Handler] = {}


def register(card_kind: str, handler: Handler) -> None:
    HANDLERS[card_kind] = handler


def handler_for(card_kind: str) -> Handler | None:
    return HANDLERS.get(card_kind)
