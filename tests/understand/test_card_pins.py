"""SR-101 EX-5 for cards: a yes to a trial card confirms the version the card showed, never a
version the owner has not seen (SR-130 EX-2: it asks which version instead)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.understand import cardstore, read, trial
from understand.fakes import as_worker
from understand.test_read_apply import approvals, entries_of, write_applied
from understand.test_read_job import SESSION, log_prompt, make_core, open_card, record_text

pytestmark = pytest.mark.sr("SR-214")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(2), record_text(3)])


def edit(repo: Path, write_record, n: int) -> None:
    write_record(repo, record_text(n).replace(f"statement {n}", f"statement {n} changed"))


def candidate(core, record_id: str):
    return trial.Candidate(core.index()[record_id], 0.95, {}, "")


def answer_yes(core, card_item: str, message: str = "yes"):
    digest = log_prompt(core, message)
    job = read.build(core, SESSION, message={"digest": digest, "text": message})
    entry = {"id": card_item, "hash": "", "answer": "accepted", "evidence": message,
             "confidence": 0.99}
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [entry]})
    write_applied(core, applied)
    return open_core(core.root), applied


def test_the_card_question_keeps_the_hash_it_showed(core) -> None:
    card = trial.card(core, candidate(core, "SR-002"))
    assert card.questions[0].hash == core.index()["SR-002"].hash


def test_a_trial_yes_after_the_record_was_edited_confirms_nothing(
        repo: Path, write_record, core) -> None:
    card = trial.card(core, candidate(core, "SR-002"))
    open_card(core, card)
    shown = core.index()["SR-002"].hash
    edit(repo, write_record, 2)
    core = open_core(repo)
    assert core.index()["SR-002"].hash != shown
    after, applied = answer_yes(core, f"{card.id}/{card.questions[0].id}")
    assert approvals(after) == {} and entries_of(after, "approval") == []
    opened = {c.id: c for c in cardstore.load(after.root, SESSION)}
    assert card.id not in opened                                   # the stale card is closed
    (fresh,) = [c for c in opened.values() if c.kind == "choice"]   # which version is asked
    assert fresh.questions[0].hash == core.index()["SR-002"].hash
    assert applied.notes                                           # and the owner is told


def test_a_trial_yes_on_an_unchanged_record_still_confirms_the_shown_version(
        core) -> None:
    card = trial.card(core, candidate(core, "SR-002"))
    open_card(core, card)
    after, _ = answer_yes(core, f"{card.id}/{card.questions[0].id}")
    assert approvals(after)["SR-002"]["records"][0]["hash"] == card.questions[0].hash


