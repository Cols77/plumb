"""SP7 slice 2: one answer path for the owner's words and the owner's clicks (C5). The words
path is covered by the reader's tests; these pin what a button source does differently."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.test_read_job import SESSION, make_core, open_card, record_text

from plumb.contracts import Choice
from plumb.understand import answer, trial

pytestmark = pytest.mark.sr("SR-101")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 3)])


def trial_card(core, record_id: str):
    return trial.card(core, trial.Candidate(core.index()[record_id], 0.9, {}))


def press(core, card, choice: Choice):
    work = answer.Answering(core, SESSION)
    question = card.questions[0]
    answer.apply_answer(work, card=card.id, question=question.id, record=question.record,
                        hash=question.hash, choice=choice,
                        source=answer.Button(offer_id="offer-1", key_digest="sha256:k"))
    return work.applied()


def test_confirm_pressed_writes_an_owner_button_approval_at_the_shown_hash(core) -> None:
    card = trial_card(core, "SR-001")
    open_card(core, card)
    applied = press(core, card, Choice(label="Confirm", answer="accepted"))
    (entry,) = [e for e in applied.entries if e["kind"] == "approval"]
    payload = entry["payload"]
    assert payload["by"] == "owner" and payload["via"] == "button"
    assert payload["offer"] == "offer-1" and payload["card"] == card.id
    assert payload["records"][0]["id"] == "SR-001"
    assert payload["records"][0]["hash"] == card.questions[0].hash
    assert payload["label"] == "yes"
    assert card.id in applied.closed


@pytest.mark.parametrize(("said", "status"), [("open", "left_open"),
                                              ("change", "change_requested")])
def test_leave_open_and_ask_for_a_change_confirm_nothing(core, said: str, status: str) -> None:
    card = trial_card(core, "SR-002")
    open_card(core, card)
    applied = press(core, card, Choice(label="x", answer=said))   # type: ignore[arg-type]
    assert applied.entries == () and applied.closed == ()
    (after,) = applied.cards
    assert after.id == card.id and after.status == status and after.answers == ()


@pytest.mark.sr("SR-086")
def test_a_pick_carrying_its_wording_is_applied_not_left_waiting(core) -> None:
    """A ``change`` choice that carries its wording (a version, an option) is a pick, applied
    like any answer; only Ask for a change (no wording) leaves the card ``change_requested``."""
    assert answer.is_left(Choice("Ask for a change", "change", None))
    assert answer.is_left(Choice("Leave open", "open", None))
    assert not answer.is_left(Choice("the second version", "change", "the second version"))
    card = trial_card(core, "SR-002")
    open_card(core, card)
    applied = press(core, card, Choice("the second version", "change", "the second version"))
    (after,) = applied.cards
    assert after.status == "answered" and card.id in applied.closed
    assert [a.answer for a in after.answers] == ["change: the second version"]


@pytest.mark.sr("SR-130")
def test_an_answer_to_a_record_that_changed_asks_which_version(
        core, repo: Path, write_record) -> None:
    from plumb.api import open_core

    card = trial_card(core, "SR-001")
    open_card(core, card)
    write_record(repo, record_text(1).replace("statement 1", "a different statement"))
    applied = press(open_core(repo), card, Choice(label="Yes", answer="accepted"))
    assert [e for e in applied.entries if e["kind"] == "approval"] == []     # nothing confirmed
    assert card.id in applied.closed
    (asked,) = [c for c in applied.cards if c.kind == "choice"]
    (question,) = asked.questions
    assert question.text == "Which version do you mean?"
    assert [(c.label, c.answer) for c in question.choices] == [
        ("Keep what you answered", "change"), ("Keep how it reads now", "accepted"),
        ("Reword it", "change")]
    assert question.choices[0].change == "statement 1"
    assert "different statement" in asked.issue and "statement 1" in asked.issue
    assert asked.issue.startswith("Which version do you mean?")     # the panel draws the issue
    assert "What changes:" in asked.evidence and "Raised by:" in asked.evidence
    assert question.choices[0].consequence
