"""SR-187: a message that answers a card and adds a request has the answer applied to the card
and the new request read back; the model is scripted."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from understand.test_answer_once import FORMAT, _reply
from understand.test_clarify_job import _asked, _by_kind, _cards

pytestmark = pytest.mark.sr("SR-187")
WORDS = "2, and also make the pane resizable"
READS = "make the pane resizable"


def _answering(repo: Path, world: Any, readback: dict[str, Any]) -> tuple[str, Any]:
    _asked("let users export their data", FORMAT, repo, world)
    (card,) = _by_kind(repo, "choice")
    first = {c.id for c in _cards(repo)}
    _reply(repo, world, WORDS,
           [{"id": f"{card.id}/format", "hash": "", "answer": "change", "change": "2",
             "evidence": "2", "confidence": 0.95}],
           {"intent": "yes", "answers": {"card": card.id, "evidence": "2", "also": READS},
            "readback": readback, "replaces": [card.id]})
    return card.id, [c for c in _cards(repo) if c.id not in first]


def test_ex2_the_card_is_answered_and_only_the_new_request_is_read_back(
        repo: Path, engine_standins: Any) -> None:
    card, new = _answering(repo, engine_standins, {"proposal": f"Your request: {READS}"})
    assert {c.id: c.status for c in _cards(repo)}[card] == "answered"
    (readback,) = new
    assert READS in readback.issue and WORDS not in readback.issue


def test_ex4_an_unclear_new_request_is_read_back_with_what_was_unclear(
        repo: Path, engine_standins: Any) -> None:
    card, new = _answering(repo, engine_standins, {
        "proposal": f"Your request: {READS}", "assumptions": ["resizable by dragging or by menu"]})
    assert {c.id: c.status for c in _cards(repo)}[card] == "answered"
    (readback,) = new
    assert "resizable by dragging or by menu" in readback.evidence
