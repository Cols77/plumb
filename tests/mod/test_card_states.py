"""SR-160: an answered card leaves the waiting list at once, and the panel's data groups the
session's cards as waiting, processing, blocked (with why) and done."""

from __future__ import annotations

from pathlib import Path

import pytest
from mod.helpers import DIGEST, KEY, SESSION, run_mod, sample_card
from mod.test_press import CONFIRM, _edit, _offer, _press
from understand.test_read_job import make_core, open_card, record_text

from plumb.understand import cardstore, summary

pytestmark = pytest.mark.sr("SR-268")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 4)])


def _draw(core, monkeypatch, capsys) -> dict:
    assert run_mod(monkeypatch, capsys, core.root, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0
    return answer


def _states(answer: dict) -> dict[str, str]:
    return {c["id"]: c["state"] for c in answer["cards"]}


def test_a_pressed_card_leaves_waiting_then_shows_done(core, monkeypatch, capsys) -> None:
    # EX-1: the press is logged; its answer is not applied yet (the card is still open)
    open_card(core, sample_card(core, "SR-001"))
    drawn = _draw(core, monkeypatch, capsys)
    offer = _offer(drawn)
    summary._waiting(core, SESSION, ["t"], ["card:SR-001"])
    assert "1 cards" in summary.waiting_line(core.root, SESSION, core)
    core.log_append("events", "card-press", {
        "session": SESSION, "offer": offer["offer_id"], "card": "card:SR-001", "question": offer["question"],
        "choice": CONFIRM, "answer": "accepted", "label": "Yes", "record": "SR-001",
        "hash": offer["hash"], "key_digest": DIGEST})
    assert summary.waiting_line(core.root, SESSION, core) is None
    assert cardstore.states(core, SESSION)["card:SR-001"][0] == "processing"
    again = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})[1]
    (card,) = again["cards"]
    assert (card["state"], card["repeats"]) == ("processing", False)
    # applied: the same card is under done
    assert _press(monkeypatch, capsys, core.root, offer["offer_id"], CONFIRM)[0] == 0
    assert cardstore.states(core, SESSION)["card:SR-001"][0] == "done"


def test_an_answer_on_a_changed_record_is_blocked_with_the_reason(core, monkeypatch, capsys) -> None:
    # EX-2
    open_card(core, sample_card(core, "SR-001"))
    offer = _offer(_draw(core, monkeypatch, capsys))
    _edit(core.root)
    assert _press(monkeypatch, capsys, core.root, offer["offer_id"], CONFIRM)[0] == 0
    state, reason = cardstore.states(open_core_of(core), SESSION)["card:SR-001"]
    assert state == "blocked" and "changed since it was shown" in reason
    drawn = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})[1]
    (card,) = [c for c in drawn["settled"] if c["id"] == "card:SR-001"]
    assert (card["state"], card["reason"]) == ("blocked", reason)


def test_three_cards_waiting_are_all_waiting(core, monkeypatch, capsys) -> None:
    # EX-3
    for n in (1, 2, 3):
        open_card(core, sample_card(core, f"SR-00{n}"))
    drawn = _draw(core, monkeypatch, capsys)
    assert list(_states(drawn).values()) == ["waiting"] * 3
    assert {c["state"] for c in drawn["cards"]} == {"waiting"}


def open_core_of(core):
    from plumb.api import open_core

    return open_core(core.root)


def test_a_confirmed_card_stays_done_after_the_record_is_edited(core, monkeypatch, capsys) -> None:
    open_card(core, sample_card(core, "SR-001"))
    offer = _offer(_draw(core, monkeypatch, capsys))
    assert _press(monkeypatch, capsys, core.root, offer["offer_id"], CONFIRM)[0] == 0
    _edit(core.root)
    assert cardstore.states(open_core_of(core), SESSION)["card:SR-001"][0] == "done"
