"""SP7 slice 1 (sp7-realign-sp8 C2): every card kind's suggested resolutions carry their
choices as data, in the order of the resolutions, and the reader's inputs list them."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plumb.contracts import Choice, ClarifyQuestion
from plumb.present import owner_text as words
from plumb.understand import cards, cardstore

pytestmark = [pytest.mark.sr("SR-105"), pytest.mark.sr("SR-101")]

SESSION = "s1"


def record(n: int = 1, title: str = "Export as CSV") -> SimpleNamespace:
    return SimpleNamespace(id=f"SR-{n:03d}", title=title, hash=f"sha256:{n:064d}",
                           fields={"statement": title, "quote": "export it as csv"})


def answers(question: ClarifyQuestion) -> list[tuple[str, str, str | None]]:
    assert [c.label for c in question.choices] == list(question.resolutions)
    return [(c.label, c.answer, c.change) for c in question.choices]


def test_trial_yes_is_accepted_no_is_rejected_fix_it_is_a_change() -> None:
    from plumb.understand import trial

    assert [(c.label, c.answer, c.change) for c in trial.CHOICES] == [
        ("Yes", "accepted", None), ("No", "rejected", None), ("Fix it", "change", None)]
    assert all(c.consequence for c in trial.CHOICES)


def test_beyond_keep_drop_reword() -> None:
    card = cards.beyond_card({}, record(), ["adds a header row"], {"messages": []})
    (question,) = card.questions
    assert answers(question) == [(words.BEYOND_KEEP, "accepted", None),
                                 (words.BEYOND_DROP, "rejected", None),
                                 (words.BEYOND_REWORD, "change", None)]


def test_contradicts_a_version_is_a_change_carrying_it_and_combine_is_a_change() -> None:
    card = cards.contradicts_card({}, record(), ["you said JSON before"], {"messages": []})
    (question,) = card.questions
    assert answers(question) == [
        ("Keep this one", "change", "Keep the record as it reads"),
        ("Keep the other", "change", "Keep what you said instead of the record"),
        ("Both", "change", None)]
    assert all(c.consequence for c in question.choices)       # SR-130 EX-3: what each means


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


def test_couldnt_check_build_anyway_is_accepted_and_wait_is_rejected() -> None:
    from plumb.understand import clarify

    (question,) = clarify.couldnt_check_card("sha256:" + "a" * 64).questions
    assert answers(question) == [(words.GATE_WAIT, "rejected", None),
                                 (words.GATE_BUILD_ANYWAY, "accepted", None)]
    assert all(c.consequence for c in question.choices)


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


def test_stale_link_options_are_picks_carrying_their_wording() -> None:
    from plumb.contracts import CardState
    from plumb.mod import offers

    options = ("Update the test to the new wording", "Keep the old wording")
    drawn = offers.buttons(CardState(id="stale:L1", kind="stale_link", resolutions=options), None)
    assert drawn[:2] == tuple(Choice(o, "change", o) for o in options)
    assert [b.label for b in drawn[2:]] == [words.BUTTON_ASK_CHANGE, words.BUTTON_LEAVE_OPEN]


def test_choices_survive_the_card_store(tmp_path: Path) -> None:
    card = cards.beyond_card({}, record(), ["adds a header row"], {"messages": []})
    cardstore.save(tmp_path, SESSION, [card])
    (back,) = cardstore.own_cards(tmp_path, SESSION)
    assert back.questions[0].choices == card.questions[0].choices


def test_the_reader_inputs_list_each_question_s_choices(repo: Path, write_record) -> None:
    from plumb.api import open_core
    from plumb.understand import files, read

    core = open_core(repo)
    beyond = cards.beyond_card({}, record(), ["adds a header row"], {"messages": []})
    cardstore.save(core.root, SESSION, [beyond])
    files.write_json_atomic(files.stale_cards_path(core.root, SESSION), [{
        "link": "L1", "record": "SR-001", "path": "tests/test_x.py", "topic": "Export",
        "issue": "the test moved", "options": ["Repin it", "Leave it"], "recommended": 1}])
    items = {i["card"]: i for i in read.card_items(core, SESSION)}
    assert items[beyond.id]["choices"] == [
        files.choice_to_json(c) for c in beyond.questions[0].choices]
    assert [c["answer"] for c in items[beyond.id]["choices"]] == ["accepted", "rejected", "change"]
    assert items["stale:L1"]["choices"] == [
        {"label": "Leave it", "answer": "change", "change": "Leave it", "consequence": ""},
        {"label": "Repin it", "answer": "change", "change": "Repin it", "consequence": ""}]
    json.dumps(items)                # the job file holds them as written
