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


def test_each_press_is_a_labelled_owner_answer_and_calibration_counts_the_no(
        batch, repo: Path, monkeypatch, capsys) -> None:
    from plumb.capture import jevcmd

    ids, cards = batch
    offer = {r: c["offers"][0] for r, c in cards.items()}
    code, yes, _ = _press(monkeypatch, capsys, repo, offer["SR-001"], "accepted")
    assert code == 0 and yes["confirmed"] == ["SR-001"] and yes["status"] == "closed"
    code, no, _ = _press(monkeypatch, capsys, repo, offer["SR-002"], "rejected")
    assert code == 0 and no["rejected"] == ["SR-002"]
    code, last, _ = _press(monkeypatch, capsys, repo, offer["SR-003"], "accepted")
    assert code == 0 and last["confirmed"] == ["SR-003"] and last["status"] == "closed"
    events = open_core(repo).events()
    (approval,) = [e for e in events if e.kind == "approval"
                   and e.payload["records"][0]["id"] == "SR-001"]
    assert (approval.payload["by"], approval.payload["via"], approval.payload["label"]) == (
        "owner", "button", "yes")
    (rejection,) = [e for e in events if e.kind == "rejection"]
    assert (rejection.payload["by"], rejection.payload["via"], rejection.payload["reason"]) \
        == ("owner", "button", "capture-error")
    assert rejection.payload["records"][0]["kind"] == "example-restatement"
    trials = [e for e in events if e.kind == "trial"]
    assert sorted(a["answer"] for t in trials for a in t.payload["answers"]) == [
        "accepted", "accepted", "rejected"]
    # the next turn end reruns the calibration from the logged scores, no model call
    _turn_end(repo)
    fresh = open_core(repo)
    calibrations = [e for e in fresh.events() if e.kind == "calibration"]
    assert calibrations and calibrations[-1].payload["source"] == "logged"
    counted = calibrations[-1].payload["per_kind"]["example-restatement"]
    assert counted["positives"] == 2 and counted["real_negatives"] == 1
    status = jevcmd.jev_status(fresh)
    assert status["calibration"]["example-restatement"]["real_no"] == 1
    # a rejected or confirmed record is not offered again
    assert not [c for c in cardstore.own_cards(repo, SESSION)
                if c.kind == "trial" and c.status == "open"]


def _fixture(name: str) -> Any:
    import json
    import re

    text = (Path(__file__).resolve().parents[2] / "tests" / "plugin" / "mod"
            / "fixtures.ts").read_text(encoding="utf-8")
    found = re.search(rf"// BEGIN {name}\n.*?= (.*?)\n// END {name}", text, re.S)
    assert found, name
    return json.loads(found.group(1))


def test_the_panels_trial_fixtures_have_the_shape_of_a_real_trial_draw_and_press(
        batch, repo: Path, monkeypatch, capsys) -> None:
    ids, cards = batch
    card = cards["SR-001"]
    (fixture,) = _fixture("DRAW_TRIAL")["cards"]
    assert set(fixture) == set(card) and fixture["kind"] == card["kind"] == "trial"
    assert set(fixture["questions"][0]) == set(card["questions"][0])
    assert set(fixture["offers"][0]) == set(card["offers"][0])
    assert [b["answer"] for b in fixture["offers"][0]["buttons"]][:2] == [
        b["answer"] for b in card["offers"][0]["buttons"]][:2]
    assert {o["question"] for o in fixture["offers"]} == {q["id"] for q in fixture["questions"]}
    code, pressed, _ = _press(monkeypatch, capsys, repo, card["offers"][0], "rejected")
    shown = _fixture("PRESS_TRIAL_NO")
    assert code == 0 and set(shown) == set(pressed)
    assert (shown["answer"], shown["status"]) == (pressed["answer"], pressed["status"])
    assert "marked wrong" in shown["line"] and "marked wrong" in pressed["line"]


def test_a_record_answered_is_not_offered_again(batch, repo: Path, monkeypatch,
                                                 capsys) -> None:
    ids, cards = batch
    assert _press(monkeypatch, capsys, repo, cards["SR-001"]["offers"][0], "accepted")[0] == 0
    again = _trial(_draw(monkeypatch, capsys, repo))
    assert sorted(again) == ["SR-002", "SR-003"]
    # each offer is still the one first drawn for its record
    assert {r: c["offers"][0]["offer_id"] for r, c in again.items()} == {
        r: cards[r]["offers"][0]["offer_id"] for r in ("SR-002", "SR-003")}


def test_the_calibration_reruns_at_the_turn_end_and_counts_every_press(
        batch, repo: Path, monkeypatch, capsys) -> None:
    """SR-106: calibration reruns from the logged scores at the turn end after an answer; the
    next rerun counts the yes pressed since."""
    ids, cards = batch
    offer = {r: c["offers"][0] for r, c in cards.items()}
    assert _press(monkeypatch, capsys, repo, offer["SR-001"], "accepted")[0] == 0
    _turn_end(repo)
    (first,) = [e for e in open_core(repo).events() if e.kind == "calibration"]
    assert first.payload["per_kind"]["example-restatement"]["positives"] == 1
    assert _press(monkeypatch, capsys, repo, offer["SR-002"], "accepted")[0] == 0
    assert _press(monkeypatch, capsys, repo, offer["SR-003"], "accepted")[0] == 0
    _turn_end(repo)
    calibration = [e for e in open_core(repo).events() if e.kind == "calibration"][-1]
    assert calibration.payload["source"] == "logged"
    assert calibration.payload["per_kind"]["example-restatement"]["positives"] == 3


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


def test_a_record_held_by_leave_open_comes_back_once_it_changes(
        batch, repo: Path, write_record, monkeypatch, capsys) -> None:
    """DEC-034: a trial card left open holds its records; once one of them changes the card is
    open again (``reopen_changed``) and repeats in the next draw; while nothing changed it stays
    left open."""
    from plumb.mod import offers

    ids, cards = batch
    card = cards["SR-002"]
    assert _press(monkeypatch, capsys, repo, cards["SR-001"]["offers"][0], "accepted")[0] == 0
    assert _press(monkeypatch, capsys, repo, card["offers"][0], "open")[0] == 0
    assert offers.reopen_changed(open_core(repo), SESSION) == []
    held = [c for c in cardstore.own_cards(repo, SESSION) if c.id == card["id"]]
    assert [c.status for c in held] == ["left_open"]
    write_record(repo, requirement_text(
        2, "Operation 2", "The calculator does operation 2 on whole numbers", intent=1,
        examples=(("input 2", "it runs", "output 2"),)))
    assert offers.reopen_changed(open_core(repo), SESSION) == [card["id"]]
    (back,) = [c for c in cardstore.own_cards(repo, SESSION) if c.id == card["id"]]
    assert back.status == "open"
    again = _trial(_draw(monkeypatch, capsys, repo))["SR-002"]
    assert again["id"] == card["id"] and again["repeats"] is True
