"""SR-129: the read-back card shows the proposal, the assumptions and the one thing not done."""
from __future__ import annotations

from pathlib import Path

from plumb.understand import clarify

READBACK = {"proposal": "Work in a worktree and merge at the end.",
            "will": ["build it in a worktree", "merge at the end"],
            "wont": ["touch main", "rewrite history"],
            "assumptions": ["the findings are the ones listed above"],
            "examples": ["one worktree per finding"]}


def _card(root: Path):
    return clarify._readback_card(root, "sha256:" + "ab" * 32, "do the findings above",
                                  READBACK, ["Assumed: the findings are the ones listed above"])


def test_ex1_the_card_has_the_proposal_the_assumptions_and_one_wont(tmp_path: Path) -> None:
    card = _card(tmp_path)
    assert card.issue == "Work in a worktree and merge at the end."
    assert card.evidence.splitlines() == [
        "Assumed: the findings are the ones listed above", "Not doing: touch main"]
    for word in ("I will", "For example", "rewrite history", "one worktree per finding"):
        assert word not in card.evidence + card.issue


def test_ex2_the_card_names_its_request_and_date(tmp_path: Path) -> None:
    card = _card(tmp_path)
    assert card.topic.startswith("Your request of 20")
    assert card.topic.endswith('"do the findings above"')


def test_ex3_the_card_uses_the_owners_words_only(tmp_path: Path) -> None:
    card = _card(tmp_path)
    text = " ".join([card.topic, card.issue, card.evidence, card.questions[0].text,
                     *card.resolutions, *(c.consequence for c in card.questions[0].choices)])
    for word in ("settled", "trial", "relay", "sha256", "clarify:"):
        assert word not in text


def test_the_assumptions_still_come_from_the_stored_card(tmp_path: Path) -> None:
    assert clarify.assumptions(_card(tmp_path)) == [
        ("the findings are the ones listed above", "proposed")]
