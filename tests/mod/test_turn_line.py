"""SR-159: with the panel running, the end-of-turn text is one short plumb line, no card content."""

from __future__ import annotations

import dataclasses
import json

import pytest
from mod.test_handshake import _present, _register, _start_turn, _stop, core  # noqa: F401

from plumb.understand import cardstore

pytestmark = pytest.mark.sr("SR-159")


def _message(out: str) -> str:
    return json.loads(out)["systemMessage"] if out.strip() else ""


def test_one_new_card_gives_one_plumb_line_and_no_card_content(
        core, monkeypatch, capsys, hook_input) -> None:  # noqa: F811
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    message = _message(_stop(core.root, hook_input))
    assert message == "plumb: 1 new card waits on the panel"
    assert _present(core.root)["cards"]


def test_an_applied_answer_is_named_by_the_card_title(
        core, monkeypatch, capsys, hook_input) -> None:  # noqa: F811
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    _stop(core.root, hook_input)
    cards = cardstore.load(core.root, "s1", open_only=False)
    cardstore.save(core.root, "s1", [dataclasses.replace(c, status="answered") for c in cards])
    assert _message(_stop(core.root, hook_input)) == f"plumb: your answer on {cards[0].topic} was applied"


def test_without_a_panel_the_card_prints_in_full(core, hook_input) -> None:  # noqa: F811
    _start_turn(core.root)
    assert "Requirement 1" in _message(_stop(core.root, hook_input))


def test_a_turn_where_nothing_about_cards_changed_prints_nothing(
        core, monkeypatch, capsys, hook_input) -> None:  # noqa: F811
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    _stop(core.root, hook_input)
    assert _message(_stop(core.root, hook_input)) == ""
