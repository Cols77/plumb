"""SR-101 EX-5 for cards: a yes to a trial, backlog or show-first card confirms the version
the card showed, never a version the owner has not seen."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.contracts import Applied
from plumb.understand import backlog, cardstore, read, trial
from understand.fakes import as_worker
from understand.test_read_apply import approvals, entries_of, write_applied
from understand.test_read_job import SESSION, log_prompt, make_core, open_card, record_text

pytestmark = pytest.mark.sr("SR-101")


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
    card = trial.individual_card(candidate(core, "SR-002"))
    assert card.questions[0].hash == core.index()["SR-002"].hash
    other = backlog.fragment_card(core.index()["SR-003"])
    assert other.questions[0].hash == core.index()["SR-003"].hash
    first = read.show_first_card(core.index()["SR-002"], "words")
    assert first.questions[0].hash == core.index()["SR-002"].hash


def test_a_trial_yes_after_the_record_was_edited_confirms_nothing(
        repo: Path, write_record, core) -> None:
    card = trial.individual_card(candidate(core, "SR-002"))
    open_card(core, card)
    shown = core.index()["SR-002"].hash
    edit(repo, write_record, 2)
    core = open_core(repo)
    assert core.index()["SR-002"].hash != shown
    after, applied = answer_yes(core, f"{card.id}/{card.questions[0].id}")
    assert approvals(after) == {} and entries_of(after, "approval") == []
    opened = {c.id: c for c in cardstore.load(after.root, SESSION)}
    assert card.id not in opened                                   # the stale card is closed
    fresh = opened["show_first:SR-002"]                            # the new version is shown
    assert fresh.questions[0].hash == core.index()["SR-002"].hash
    assert applied.notes                                           # and the owner is told


def test_a_trial_yes_on_an_unchanged_record_still_confirms_the_shown_version(
        core) -> None:
    card = trial.individual_card(candidate(core, "SR-002"))
    open_card(core, card)
    after, _ = answer_yes(core, f"{card.id}/{card.questions[0].id}")
    assert approvals(after)["SR-002"]["records"][0]["hash"] == card.questions[0].hash


def test_a_show_first_yes_after_the_record_was_edited_confirms_nothing(
        repo: Path, write_record, core) -> None:
    card = read.show_first_card(core.index()["SR-003"], "words")
    open_card(core, card)
    edit(repo, write_record, 3)
    core = open_core(repo)
    after, _ = answer_yes(core, f"{card.id}/{card.questions[0].id}")
    assert approvals(after) == {}
    opened = {c.id: c for c in cardstore.load(after.root, SESSION)}
    assert opened["show_first:SR-003"].questions[0].hash == core.index()["SR-003"].hash
    assert opened["show_first:SR-003"].questions[0].hash != card.questions[0].hash


def test_a_backlog_yes_after_the_record_was_edited_confirms_nothing(
        repo: Path, write_record, core) -> None:
    card = backlog.fragment_card(core.index()["SR-003"])
    open_card(core, card)
    edit(repo, write_record, 3)
    core = open_core(repo)
    after, _ = answer_yes(core, f"{card.id}/{card.questions[0].id}")
    assert approvals(after) == {}
    assert "show_first:SR-003" in {c.id for c in cardstore.load(after.root, SESSION)}


def test_a_whole_card_yes_confirms_each_record_only_at_the_version_shown(
        repo: Path, write_record, core) -> None:
    card = backlog.feature_card("Maths", [candidate(core, "SR-002"), candidate(core, "SR-003")],
                                None)
    edit(repo, write_record, 3)
    core = open_core(repo)
    confirmed: list[tuple[str, str]] = []

    def confirm(record, record_hash, evidence, confidence, label=None) -> None:
        confirmed.append((record, record_hash))

    result = backlog.effect(core=core, card=card, question=None, accepted=True, confirm=confirm,
                            entry={"evidence": "yes", "confidence": 0.99})
    assert confirmed == [("SR-002", card.questions[0].hash)]
    assert isinstance(result, Applied)
    assert [c.id for c in result.cards] == ["show_first:SR-003"]
