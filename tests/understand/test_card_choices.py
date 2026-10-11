"""SP7 slice 1 (sp7-realign-sp8 C2): every card kind's suggested resolutions carry their
choices as data, in the order of the resolutions, and the reader's inputs list them."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plumb.contracts import CardState, Choice, ClarifyQuestion
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


def test_trial_yes_is_accepted_and_no_is_rejected() -> None:
    from plumb.understand import trial

    item = trial.Candidate(record(), 0.95, {"messages": [{"text": "csv please"}]})
    for card in (trial.individual_card(item), trial.batch_card([item, item], 0.9)):
        for question in card.questions:
            assert answers(question) == [(words.TRIAL_YES, "accepted", None),
                                         (words.TRIAL_NO, "rejected", None)]


def test_backlog_feature_card_yes_except_no() -> None:
    from plumb.understand import backlog

    item = SimpleNamespace(record=record(), premise={"messages": [{"text": "csv"}]})
    drawn = SimpleNamespace(record=record(2, "Export as JSON"), premise={})
    card = backlog.feature_card("exports", [item], drawn)
    assert len(card.questions) == 2
    for question in card.questions:
        assert answers(question) == [(words.BACKLOG_YES, "accepted", None),
                                     (words.BACKLOG_EXCEPT, "change", None),
                                     (words.BACKLOG_NO, "rejected", None)]


def test_backlog_card_without_the_original_words_accept_or_correct() -> None:
    from plumb.understand import backlog

    (question,) = backlog.fragment_card(record()).questions
    assert answers(question) == [(words.NO_ORIGINAL_ACCEPT, "accepted", None),
                                 (words.NO_ORIGINAL_CORRECT, "change", None)]


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
        (words.CONTRADICTS_KEEP_OLD, "change", words.CONTRADICTS_KEEP_OLD),
        (words.CONTRADICTS_KEEP_NEW, "change", words.CONTRADICTS_KEEP_NEW),
        (words.CONTRADICTS_COMBINE, "change", None)]


def test_couldnt_check_build_anyway_is_accepted_and_wait_is_rejected() -> None:
    from plumb.understand import clarify

    (question,) = clarify.couldnt_check_card("sha256:" + "a" * 64).questions
    assert answers(question) == [(words.GATE_BUILD_ANYWAY, "accepted", None),
                                 (words.GATE_WAIT, "rejected", None)]


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


def test_show_first_yes_is_accepted_and_no_is_rejected() -> None:
    from plumb.understand import read

    (question,) = read.show_first_card(record(), "SR-001 is fine").questions
    assert answers(question) == [(words.SHOW_FIRST_YES, "accepted", None),
                                 (words.SHOW_FIRST_NO, "rejected", None)]
    undone = cards.choices_for("show_first", (words.UNDONE_CONFIRM, words.UNDONE_CHANGE,
                                              words.UNDONE_DROP))
    assert [(c.answer, c.change) for c in undone] == [("accepted", None), ("change", None),
                                                      ("rejected", None)]


def test_settle_offer_turn_on_is_accepted_and_leave_off_is_rejected() -> None:
    from plumb.understand import settle

    card = settle.offer_card("intent")
    assert cards.choices_for(card.kind, card.resolutions) == (
        Choice(words.SETTLE_TURN_ON.format(kind="intent"), "accepted"),
        Choice(words.SETTLE_LEAVE_OFF, "rejected"))


def test_stale_link_options_are_picks_carrying_their_wording() -> None:
    options = ("Update the test to the new wording", "Keep the old wording")
    assert cards.choices_for("stale_link", options) == tuple(
        Choice(o, "change", o) for o in options)


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
    stored_before = CardState(       # a card written before choices: its kind's are listed
        id="trial:old", kind="trial", topic="Export", issue="right?",
        questions=(ClarifyQuestion(id="q1", text="Export",
                                   resolutions=(words.TRIAL_YES, words.TRIAL_NO)),))
    cardstore.save(core.root, SESSION, [beyond, stored_before])
    files.write_json_atomic(files.stale_cards_path(core.root, SESSION), [{
        "link": "L1", "record": "SR-001", "path": "tests/test_x.py", "topic": "Export",
        "issue": "the test moved", "options": ["Repin it", "Leave it"], "recommended": 1}])
    items = {i["card"]: i for i in read.card_items(core, SESSION)}
    assert items[beyond.id]["choices"] == [
        {"label": words.BEYOND_KEEP, "answer": "accepted", "change": None},
        {"label": words.BEYOND_DROP, "answer": "rejected", "change": None},
        {"label": words.BEYOND_REWORD, "answer": "change", "change": None}]
    assert [c["answer"] for c in items["trial:old"]["choices"]] == ["accepted", "rejected"]
    assert items["stale:L1"]["choices"] == [
        {"label": "Leave it", "answer": "change", "change": "Leave it"},
        {"label": "Repin it", "answer": "change", "change": "Repin it"}]
    json.dumps(items)                # the job file holds them as written
