"""SP7 slice 2: one answer path for the owner's words and the owner's clicks (C5). The words
path is covered by the reader's tests; these pin what a button source does differently."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.test_read_job import SESSION, make_core, open_card, record_text

from plumb.contracts import Choice
from plumb.understand import answer, read

pytestmark = pytest.mark.sr("SR-101")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 3)])


def press(core, card, choice: Choice):
    work = answer.Answering(core, SESSION)
    question = card.questions[0]
    answer.apply_answer(work, card=card.id, question=question.id, record=question.record,
                        hash=question.hash, choice=choice,
                        source=answer.Button(offer_id="offer-1", key_digest="sha256:k"))
    return work.applied()


def test_confirm_pressed_writes_an_owner_button_approval_at_the_shown_hash(core) -> None:
    card = read.show_first_card(core.index()["SR-001"], "words")
    open_card(core, card)
    applied = press(core, card, Choice(label="Confirm", answer="accepted"))
    (entry,) = [e for e in applied.entries if e["kind"] == "approval"]
    payload = entry["payload"]
    assert payload["by"] == "owner" and payload["via"] == "button"
    assert payload["offer"] == "offer-1" and payload["card"] == card.id
    assert payload["records"][0]["id"] == "SR-001"
    assert payload["records"][0]["hash"] == card.questions[0].hash
    assert card.id in applied.closed


@pytest.mark.parametrize(("said", "status"), [("open", "left_open"),
                                              ("change", "change_requested")])
def test_leave_open_and_ask_for_a_change_confirm_nothing(core, said: str, status: str) -> None:
    card = read.show_first_card(core.index()["SR-002"], "words")
    open_card(core, card)
    applied = press(core, card, Choice(label="x", answer=said))   # type: ignore[arg-type]
    assert applied.entries == () and applied.closed == ()
    (after,) = applied.cards
    assert after.id == card.id and after.status == status and after.answers == ()
