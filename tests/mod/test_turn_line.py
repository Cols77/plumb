"""SR-159, SR-265: the end-of-turn text is one short plumb line, no card content, with the
panel running or not; the card goes to the agent (SR-266)."""

from __future__ import annotations

import dataclasses
import json

import pytest
from mod.test_handshake import _present, _register, _start_turn, _stop, core  # noqa: F401

from plumb.understand import cardstore

pytestmark = pytest.mark.sr("SR-265")


def _message(out: str) -> str:
    return json.loads(out)["systemMessage"] if out.strip() else ""


def test_one_new_card_gives_one_plumb_line_and_no_card_content(
        core, monkeypatch, capsys, hook_input) -> None:  # noqa: F811
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    message = _message(_stop(core.root, hook_input))
    assert message == "plumb: 1 question for you"
    assert _present(core.root)["cards"]


def test_an_applied_answer_is_named_by_the_card_title(
        core, monkeypatch, capsys, hook_input) -> None:  # noqa: F811
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    _stop(core.root, hook_input)
    cards = cardstore.load(core.root, "s1", open_only=False)
    cardstore.save(core.root, "s1", [dataclasses.replace(c, status="answered") for c in cards])
    assert _message(_stop(core.root, hook_input)) == f"plumb: your answer on {cards[0].topic} was applied"


def test_without_a_panel_the_line_is_the_same_and_the_card_is_the_agents(
        core, hook_input) -> None:  # noqa: F811
    _start_turn(core.root)
    assert _message(_stop(core.root, hook_input)) == "plumb: 1 question for you"
    notes = core.root / ".plumb" / "session" / "s1" / "agent_notes.json"
    assert "Requirement 1" in notes.read_text("utf-8")


def test_a_turn_where_nothing_about_cards_changed_prints_nothing(
        core, monkeypatch, capsys, hook_input) -> None:  # noqa: F811
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    _stop(core.root, hook_input)
    assert _message(_stop(core.root, hook_input)) == ""
