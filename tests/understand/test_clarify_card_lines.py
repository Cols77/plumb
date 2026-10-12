"""SR-147: the clarify card prints its questions, not the read-back's lines."""
from __future__ import annotations

from plumb.contracts import CardState
from plumb.understand import clarify, fullcard
from plumb.understand.cards import render

READBACK = {"will": ["build it in a worktree", "merge at the end"],
            "wont": ["touch main"], "assumptions": ["the findings are the ones listed above"]}


def _card(kind: str) -> CardState:
    return CardState(id="c1", kind=kind, topic="worktree changes", issue="which findings?",
                     evidence=clarify._evidence(READBACK), resolutions=("the ones above",))


def test_ex1_the_hook_prints_no_readback_lines_on_a_clarify_card() -> None:
    text = render(_card("clarify"))
    assert text.splitlines()[0].endswith("which findings?")
    assert "  1. the ones above" in text
    for word in ("I will:", "I will not:", "Assumed", "For example"):
        assert word not in text
    full = fullcard.lines({"kind": "clarify", "topic": "worktree changes",
                           "issue": "which findings?", "evidence": clarify._evidence(READBACK)})
    assert not any("I will" in line for line in full)


def test_ex2_the_assumptions_still_come_from_the_stored_card() -> None:
    assert clarify.assumptions(_card("clarify")) == [
        ("the findings are the ones listed above", "proposed")]


def test_ex3_other_cards_keep_their_evidence_line() -> None:
    card = CardState(id="c2", kind="stale_link", topic="Adds numbers", issue="a test fails now",
                     evidence="t::a passed in an earlier run and fails now")
    assert "  Evidence: t::a passed in an earlier run and fails now" in render(card)
