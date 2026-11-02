"""SR-187: a message that answers a card and adds a request has the answer applied to the card;
the new request draws no read-back card (SR-252 EX-6: the judge's questions cover its records
once captured); the model is scripted."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from understand.test_answer_once import FORMAT, _reply
from understand.test_clarify_job import _asked, plant_card, _by_kind, _cards

pytestmark = pytest.mark.sr("SR-214")
WORDS = "2, and also make the pane resizable"
READS = "make the pane resizable"


def _answering(repo: Path, world: Any, readback: dict[str, Any]) -> tuple[str, Any]:
    _asked("let users export their data", FORMAT, repo, world)
    plant_card(repo)
    (card,) = _by_kind(repo, "choice")
    first = {c.id for c in _cards(repo)}
    _reply(repo, world, WORDS,
           [{"id": f"{card.id}/format", "hash": "", "answer": "change", "change": "2",
             "evidence": "2", "confidence": 0.95}],
           {"intent": "yes", "answers": {"card": card.id, "evidence": "2", "also": READS},
            "readback": readback, "replaces": [card.id]})
    return card.id, [c for c in _cards(repo) if c.id not in first]


def test_ex2_the_card_is_answered_and_the_new_request_draws_no_read_back(
        repo: Path, engine_standins: Any) -> None:
    card, new = _answering(repo, engine_standins, {"proposal": f"Your request: {READS}"})
    assert {c.id: c.status for c in _cards(repo)}[card] == "answered"
    assert new == []


def test_ex4_an_assumption_in_the_new_request_draws_no_read_back_card(
        repo: Path, engine_standins: Any) -> None:
    card, new = _answering(repo, engine_standins, {
        "proposal": f"Your request: {READS}", "assumptions": ["resizable by dragging or by menu"]})
    assert {c.id: c.status for c in _cards(repo)}[card] == "answered"
    assert new == []
