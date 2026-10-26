"""SR-162: a background job reads the open cards against the owner's confirmed records and
withdraws the ones a confirmed record answers or that repeat another; the model is stubbed."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from plumb import stale
from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion, DispatchError
from plumb.understand import cardstore, tidy, worker
from understand.test_judge_job import SESSION, requirement_text

pytestmark = pytest.mark.sr("SR-217")

SAYS = "A conflict may be answered through the agent in chat"


@pytest.fixture
def world(repo: Path, write_record, engine_standins):
    write_record(repo, requirement_text(1, "Chat answers", SAYS))
    cardstore.save(repo, SESSION, [CardState(
        id="conflict:1", kind="conflict", topic="Answer a conflict in chat",
        issue="may a conflict be answered through the agent", resolutions=("yes", "no"),
        questions=(ClarifyQuestion(id="conflict:1#1", text="in chat?"),))])
    return engine_standins


def _run(repo: Path, confirmation: str = "confirmed") -> Any:
    core = open_core(repo)
    core.status = lambda ids: {i: types.SimpleNamespace(confirmation=confirmation,
                                                        superseded_by=None) for i in ids}
    tidy.enqueue(core, SESSION)
    worker.run_once(core, SESSION)
    return core


def _answer(world, **verdict: Any) -> None:
    world.dispatcher.script = {"tidy": {"verdicts": [{"card": "conflict:1", **verdict}]}}


def _status(repo: Path) -> str:
    return cardstore.own_cards(repo, SESSION)[0].status


def test_ex1_a_confirmed_record_that_answers_the_card_withdraws_it_quoting_it(
        repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote="through the agent in chat")
    _run(repo)
    assert _status(repo) == "withdrawn"


def test_ex2_a_record_that_is_only_proposed_leaves_the_card(repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote="through the agent in chat")
    _run(repo, "proposed")
    assert _status(repo) == "open"


def test_words_the_record_does_not_hold_leave_the_card(repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote="never in chat")
    _run(repo)
    assert _status(repo) == "open"


def test_ex3_two_stale_cards_asking_the_same_lose_one(repo: Path, write_record,
                                                      engine_standins) -> None:
    write_record(repo, requirement_text(62, "Calc", "adds"))
    for link in ("SR-062#0", "SR-062#1"):
        stale.add_card(repo, SESSION, link=link, record="SR-062", path="src/calc.py",
                       topic=f"Calc {link}", issue="the code changed", options=["keep", "undo"])
    engine_standins.dispatcher.script = {"tidy": {"verdicts": [
        {"card": "stale:SR-062#1", "verdict": "withdraw_duplicate", "other": "stale:SR-062#0"},
        {"card": "stale:SR-062#0", "verdict": "withdraw_duplicate", "other": "stale:SR-062#1"}]}}
    _run(repo)
    assert [c.id for c in cardstore.stale_cards(repo, SESSION)] == ["stale:SR-062#0"]


def test_ex4_a_judge_that_cannot_be_reached_withdraws_nothing_and_says_so(
        repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote=SAYS)
    world.dispatcher.script = {"tidy": DispatchError("run", "the model could not be reached")}
    _run(repo)
    assert _status(repo) == "open"


def test_unsure_keeps_the_card(repo: Path, world) -> None:
    _answer(world, verdict="keep")
    _run(repo)
    assert _status(repo) == "open"
