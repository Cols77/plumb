"""SR-124 (SR-106 x INT-025 x INT-032 (2), SR-133): trial cards reach the owner in the mod, one
record each, and each press is a labelled owner answer that calibration counts.

The trace: the judge's logged ``supported`` verdicts wait in the log (``trial.from_log``); the
turn end draws no trial card any more (SR-252 EX-6), so the cards here are ones opened before
(``trial.top_up``, up to three, one record each, in ``cards.json``); ``plumb mod draw``
offers each its Yes, No and Fix it; ``plumb mod press`` answers through the one answer path:
Yes is ``approval {by: owner, via: button, label: yes}``, No is a ``capture-error`` rejection
(a misreading) with the read-back it rejected; when a card is answered its ``trial`` entry is
logged; the next turn end reruns the calibration from the logged scores (no model call) and
``plumb jev status`` shows the yes and the real 'no' examples."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest
from understand.fakes import as_worker
from understand.test_judge_job import intent_text, log_prompt, requirement_text, verdict_answer

from mod.helpers import DIGEST, KEY, SESSION, run_mod
from plumb.api import open_core
from plumb.present import owner_text
from plumb.understand import cardstore, summary

MESSAGE = "Build a calculator with add, subtract, multiply, divide, power, root and modulo."


def _world(repo: Path, write_record, scores: list[float]) -> list[str]:
    from plumb.understand import judge

    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "Build a calculator", "A calculator", prompt=digest))
    ids = []
    for n in range(1, len(scores) + 1):
        write_record(repo, requirement_text(
            n, f"Operation {n}", f"The calculator does operation {n}", intent=1,
            examples=((f"input {n}", "it runs", f"output {n}"),)))
        ids.append(f"SR-{n:03d}")
    core = open_core(repo)
    job = judge.build(core, SESSION, records=ids)
    assert job is not None
    answer = verdict_answer(*((i, "supported", s) for i, s in zip(ids, scores, strict=True)))
    for given in answer["verdicts"]:       # JEV's scores: only they calibrate (SR-182)
        given.update(by="jev", judge="jev:jev-1", model="jev-1")
    applied = judge.apply(core, job, answer)
    with as_worker(repo, SESSION):         # the worker writes the verdicts; not the cards:
        for entry in applied.entries:      # the log holds them back
            core.log_append("events", entry["kind"], entry["payload"])
    return ids


def _turn_end(repo: Path) -> list[str]:
    ctx = types.SimpleNamespace(session_id=SESSION, deadline=None, extra={})
    return list(summary.stop_parts(ctx, open_core(repo), {"turn_start": 1000.0}).cards)


def _draw(monkeypatch, capsys, repo: Path) -> dict[str, Any]:
    code, answer, _ = run_mod(monkeypatch, capsys, repo, "draw", stdin={"key": KEY})
    assert code == 0
    return {c["id"]: c for c in answer["cards"]}


def _press(monkeypatch, capsys, repo: Path, offer: dict[str, Any], answer: str):
    index = next(b["index"] for b in offer["buttons"] if b["answer"] == answer)
    return run_mod(monkeypatch, capsys, repo, "press", "--offer", offer["offer_id"],
                   "--choice", str(index), stdin={"key": KEY})


def _trial(drawn: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The drawn trial cards by their record."""
    return {c["offers"][0]["record"]: c for c in drawn.values() if c["kind"] == "trial"}


@pytest.fixture
def batch(repo: Path, write_record, monkeypatch, capsys):
    """Three supported requirements held back by the log, their trial cards opened before the
    turn end stopped drawing them, the panel registered and the cards drawn:
    ``(ids, {record: card})``."""
    from plumb.understand import trial

    ids = _world(repo, write_record, [0.95, 0.9, 0.97])
    assert cardstore.own_cards(repo, SESSION) == []
    assert not any("Operation" in t for t in _turn_end(repo))     # SR-252 EX-6: none drawn
    assert cardstore.own_cards(repo, SESSION) == []
    cardstore.save(repo, SESSION, trial.top_up(open_core(repo), SESSION))
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    return ids, _trial(_draw(monkeypatch, capsys, repo))


def test_the_turn_end_puts_one_trial_card_per_record_with_yes_no_and_fix_it(batch) -> None:
    ids, cards = batch
    assert sorted(cards) == ids
    for card in cards.values():
        assert card["repeats"] is True and card["status"] == "open"
        (offer,) = card["offers"]
        assert [(b["label"], b["answer"]) for b in offer["buttons"][:3]] == [
            ("Yes", "accepted"), ("No", "rejected"), ("Fix it", "change")]



def test_a_record_answered_is_not_offered_again(batch, repo: Path, monkeypatch,
                                                 capsys) -> None:
    ids, cards = batch
    assert _press(monkeypatch, capsys, repo, cards["SR-001"]["offers"][0], "accepted")[0] == 0
    again = _trial(_draw(monkeypatch, capsys, repo))
    assert sorted(again) == ["SR-002", "SR-003"]
    # each offer is still the one first drawn for its record
    assert {r: c["offers"][0]["offer_id"] for r, c in again.items()} == {
        r: cards[r]["offers"][0]["offer_id"] for r in ("SR-002", "SR-003")}


def test_a_card_left_open_is_not_asked_again(batch, repo: Path, monkeypatch, capsys) -> None:
    ids, cards = batch
    assert _press(monkeypatch, capsys, repo, cards["SR-001"]["offers"][0], "accepted")[0] == 0
    assert _press(monkeypatch, capsys, repo, cards["SR-002"]["offers"][0], "open")[0] == 0
    _turn_end(repo)
    trials = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "trial"
              and c.questions[0].record == "SR-002"]
    assert [(c.id, c.status) for c in trials] == [(cards["SR-002"]["id"], "left_open")]


def test_a_no_on_a_trial_card_marks_the_reading_wrong_and_the_record_stays(
        batch, repo: Path, monkeypatch, capsys) -> None:
    """A trial No is a misreading (capture-error): neither the owner's line nor the agent's note
    says the record was dropped; the agent is told the record stays and is not to be removed or
    rewritten, and the record is still there, unchanged."""
    ids, cards = batch
    before = open_core(repo).index()["SR-002"].hash
    code, no, _ = _press(monkeypatch, capsys, repo, cards["SR-002"]["offers"][0], "rejected")
    assert code == 0 and no["rejected"] == ["SR-002"]
    assert no["line"] == owner_text.PRESS_MISREAD.format(label="No",
                                                         titles='"Operation 2"')
    assert no["model_note"] == owner_text.PRESS_MODEL_MISREAD.format(
        label="No", records="SR-002 'Operation 2'")
    for text in (no["line"], no["model_note"]):
        assert "dropped" not in text and "marked wrong" in text
    assert "record stays" in no["model_note"]
    assert "do not remove or rewrite it" in no["model_note"]
    assert "record stays" in no["line"]
    after = open_core(repo).index()
    assert "SR-002" in after and after["SR-002"].hash == before

