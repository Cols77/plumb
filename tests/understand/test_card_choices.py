"""SP7 slice 1 (sp7-realign-sp8 C2): every card kind's suggested resolutions carry their
choices as data, in the order of the resolutions, and the reader's inputs list them."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plumb.contracts import ClarifyQuestion
from plumb.present import owner_text as words
from plumb.understand import cards, cardstore

pytestmark = [pytest.mark.sr("SR-267"), pytest.mark.sr("SR-214")]

SESSION = "s1"


def record(n: int = 1, title: str = "Export as CSV") -> SimpleNamespace:
    return SimpleNamespace(id=f"SR-{n:03d}", title=title, hash=f"sha256:{n:064d}",
                           fields={"statement": title, "quote": "export it as csv"})


def a_conflict() -> SimpleNamespace:
    return SimpleNamespace(
        labels=("main", "feat-x"), fields={"statement": {"ours": "CSV", "theirs": "JSON"}},
        proposed=False, record="SR-001", ic="IC-1", title="Export")


def answers(question: ClarifyQuestion) -> list[tuple[str, str, str | None]]:
    assert [c.label for c in question.choices] == list(question.resolutions)
    return [(c.label, c.answer, c.change) for c in question.choices]


def test_trial_yes_is_accepted_no_is_rejected_fix_it_is_a_change() -> None:
    from plumb.understand import trial

    assert [(c.label, c.answer, c.change) for c in trial.CHOICES] == [
        ("Yes", "accepted", None), ("No", "rejected", None), ("Fix it", "change", None)]
    assert all(c.consequence for c in trial.CHOICES)


def test_sr130_ex3_a_merge_conflict_is_keep_this_keep_the_other_or_both() -> None:
    conflict = SimpleNamespace(
        labels=("main", "feat-x"), fields={"statement": {"ours": "CSV", "theirs": "JSON"}},
        proposed=False, record="SR-001", ic="IC-1", title="Export")
    card = cards.conflict_card({}, conflict)
    (question,) = card.questions
    assert answers(question) == [("Keep this one", "change", "Keep main's version"),
                                 ("Keep the other", "change", "Keep feat-x's version"),
                                 ("Both", "change", None)]
    assert "main says: What it says: CSV" in card.evidence
    assert "Keeps feat-x's version" in question.choices[1].consequence
    conflict.proposed = True                      # a combined version is already proposed
    (question,) = cards.conflict_card({}, conflict).questions
    assert [(c.label, c.answer) for c in question.choices] == [
        ("Both", "accepted"), ("Keep this one", "change"), ("Keep the other", "change")]




def test_clarify_gap_suggestions_are_picks_in_the_recommended_order() -> None:
    from plumb.understand import clarify

    question = clarify._gap_question(
        {"id": "format", "question": "Which format?", "suggestions": ["JSON", "CSV"],
         "recommended": 1}, 1)
    assert answers(question) == [("CSV", "change", "CSV"), ("JSON", "change", "JSON")]


def test_clarify_read_back_of_a_change_yes_or_not_quite() -> None:
    from plumb.understand import read

    (question,) = read.change_card(record(), "use JSON", "use JSON", "sha256:" + "b" * 64)\
        .questions
    assert answers(question) == [(words.READBACK_YES, "accepted", None),
                                 (words.READBACK_NOT_QUITE, "change", None)]


def test_choices_survive_the_card_store(tmp_path: Path) -> None:
    card = cards.conflict_card({}, a_conflict())
    cardstore.save(tmp_path, SESSION, [card])
    (back,) = cardstore.own_cards(tmp_path, SESSION)
    assert back.questions[0].choices == card.questions[0].choices


def test_the_reader_inputs_list_each_question_s_choices(repo: Path, write_record) -> None:
    from plumb.api import open_core
    from plumb.understand import files, read

    core = open_core(repo)
    conflict = cards.conflict_card({}, a_conflict())
    cardstore.save(core.root, SESSION, [conflict])
    files.write_json_atomic(files.stale_cards_path(core.root, SESSION), [{
        "link": "L1", "record": "SR-001", "path": "tests/test_x.py", "topic": "Export",
        "issue": "the test moved", "options": ["Repin it", "Leave it"], "recommended": 1}])
    items = {i["card"]: i for i in read.card_items(core, SESSION)}
    assert items[conflict.id]["choices"] == [
        files.choice_to_json(c) for c in conflict.questions[0].choices]
    assert [c["answer"] for c in items[conflict.id]["choices"]] == ["change", "change", "change"]
    assert items["stale:L1"]["choices"] == [
        {"label": "Leave it", "answer": "change", "change": "Leave it", "consequence": ""},
        {"label": "Repin it", "answer": "change", "change": "Repin it", "consequence": ""}]
    json.dumps(items)                # the job file holds them as written
