"""SR-161: a card whose question no longer stands is withdrawn by plumb, at the turn end and
right after the link it holds is settled, and the turn end says so once."""

from __future__ import annotations

import time
import types
from pathlib import Path

import pytest

from core.test_stale_resolve import (LINK, REFORMATTED, Runner, _backend, _edit,  # noqa: F401
                                     project)
from plumb import links, stale
from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion
from plumb.hosts.claude_code.hookio import Deadline, HookContext
from plumb.understand import cardstore, summary
from understand.test_judge_job import SESSION

pytestmark = pytest.mark.sr("SR-161")


def _card_for_link(root: Path) -> None:
    stale.add_card(root, SESSION, link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="the code changed", options=["keep", "undo"])


def _turn_end(core) -> str:
    # a short budget skips the upkeep, which needs models; the withdrawals do not
    ctx = HookContext("stop", {}, core.root, SESSION, Deadline(300))
    return "\n".join(summary.stop_parts(ctx, core, {"turn_start": time.time() - 60}).cards)


def test_ex1_repin_withdraws_the_stale_card_and_the_turn_end_says_so_once(project: Path) -> None:
    _edit(project, REFORMATTED)
    _card_for_link(project)
    links.repin_after_tests(open_core(project), LINK, runner=Runner(), judge=_backend("cosmetic"))
    assert cardstore.stale_cards(project, SESSION) == []
    assert "Withdrawn: SR-001#0, its link is current again" in _turn_end(open_core(project))
    assert "Withdrawn" not in _turn_end(open_core(project))
    (event,) = open_core(project).log_read("events", ["card-withdrawn"])
    assert event.payload["card"] == f"stale:{LINK}"


def test_ex4_a_still_stale_card_stays(project: Path) -> None:
    _edit(project, REFORMATTED)
    _card_for_link(project)
    assert "Withdrawn" not in _turn_end(open_core(project))
    assert [c.id for c in cardstore.stale_cards(project, SESSION)] == [f"stale:{LINK}"]


def test_unlink_withdraws_the_card_of_a_link_that_is_gone(project: Path) -> None:
    _edit(project, REFORMATTED)
    _card_for_link(project)
    links.unlink(open_core(project), LINK, "the code moved")
    assert cardstore.stale_cards(project, SESSION) == []
    assert "its link no longer exists" in _turn_end(open_core(project))


def _asked(core, **states) -> None:
    core.status = lambda ids: {i: types.SimpleNamespace(**states[i]) for i in ids}


def _read_back(kind: str, *records: str) -> CardState:
    return CardState(id=f"{kind}:1", kind=kind, topic="Pages load fast", issue="i",
                     questions=tuple(ClarifyQuestion(id=f"{kind}:1#{n}", text="q", record=r)
                                     for n, r in enumerate(records, 1)))


def test_ex2_a_trial_card_of_a_superseded_record_is_withdrawn(repo: Path) -> None:
    cardstore.save(repo, SESSION, [_read_back("trial", "SR-150")])
    core = open_core(repo)
    _asked(core, **{"SR-150": dict(confirmation="proposed", superseded_by="SR-076")})
    assert "Withdrawn: Pages load fast, SR-150 is superseded" in _turn_end(core)
    (card,) = cardstore.own_cards(repo, SESSION)
    assert card.status == "withdrawn"


def test_ex3_a_read_back_of_confirmed_records_is_withdrawn(repo: Path) -> None:
    ids = ("INT-047", "SR-155", "SR-156", "SR-157")
    cardstore.save(repo, SESSION, [_read_back("clarify", *ids)])
    core = open_core(repo)
    _asked(core, **{i: dict(confirmation="confirmed", superseded_by=None) for i in ids})
    assert "Withdrawn: Pages load fast" in _turn_end(core)
    assert cardstore.own_cards(repo, SESSION)[0].status == "withdrawn"


def test_ex3_one_record_still_proposed_keeps_the_card(repo: Path) -> None:
    ids = ("INT-047", "SR-155")
    cardstore.save(repo, SESSION, [_read_back("clarify", *ids)])
    core = open_core(repo)
    _asked(core, **{"INT-047": dict(confirmation="confirmed", superseded_by=None),
                    "SR-155": dict(confirmation="proposed", superseded_by=None)})
    assert "Withdrawn" not in _turn_end(core)
    assert cardstore.own_cards(repo, SESSION)[0].status == "open"
