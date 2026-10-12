"""SR-124 (SR-106 x INT-025 x INT-032 (2)): a trial batch reaches the owner in the mod and each press is
a labelled owner answer that calibration counts.

The trace: the judge's logged ``supported`` verdicts wait in the log (``trial.from_log``); the
stop hook's upkeep (``settle.refresh`` -> ``trial.top_up``) puts a trial batch card in
``cards.json``; ``plumb mod draw`` offers each record of the batch its own Yes and No; ``plumb
mod press`` answers through the one answer path: Yes is ``approval {by: owner, via: button,
label: yes}``, No is a ``capture-error`` rejection (a misreading) with the read-back it
rejected; when the batch is answered the ``trial`` entry is logged; the next turn end reruns
the calibration from the logged scores (no model call) and ``plumb jev status`` shows the yes
and the real 'no' examples."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest
from mod.helpers import DIGEST, KEY, SESSION, run_mod
from understand.test_judge_job import intent_text, log_prompt, requirement_text, verdict_answer

from plumb.api import open_core
from plumb.present import owner_text
from plumb.understand import cardstore, summary

pytestmark = pytest.mark.sr("SR-124")

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
    applied = judge.apply(core, job, verdict_answer(
        *((i, "supported", s) for i, s in zip(ids, scores, strict=True))))
    for entry in applied.entries:          # the worker writes the verdicts; not the cards:
        core.log_append("events", entry["kind"], entry["payload"])   # the log holds them back
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


def _trial(drawn: dict[str, Any]) -> dict[str, Any]:
    (card,) = [c for c in drawn.values() if c["kind"] == "trial"]
    return card


@pytest.fixture
def batch(repo: Path, write_record, monkeypatch, capsys):
    """Three supported requirements held back by the log, a turn end, the panel registered and
    the cards drawn."""
    ids = _world(repo, write_record, [0.95, 0.9, 0.97])
    assert cardstore.own_cards(repo, SESSION) == []
    text = _turn_end(repo)
    assert any("Operation" in t for t in text)
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    return ids, _trial(_draw(monkeypatch, capsys, repo))


def test_the_turn_end_puts_a_trial_batch_in_the_mod_with_yes_and_no_per_record(batch) -> None:
    ids, card = batch
    assert card["repeats"] is True and card["status"] == "open"
    assert sorted(o["record"] for o in card["offers"]) == ids
    for offer in card["offers"]:
        assert [(b["label"], b["answer"]) for b in offer["buttons"][:2]] == [
            (owner_text.TRIAL_YES, "accepted"), (owner_text.TRIAL_NO, "rejected")]


def test_each_press_is_a_labelled_owner_answer_and_calibration_counts_the_no(
        batch, repo: Path, monkeypatch, capsys) -> None:
    from plumb.capture import jevcmd

    ids, card = batch
    by_record = {o["record"]: o for o in card["offers"]}
    code, yes, _ = _press(monkeypatch, capsys, repo, by_record["SR-001"], "accepted")
    assert code == 0 and yes["confirmed"] == ["SR-001"]
    code, no, _ = _press(monkeypatch, capsys, repo, by_record["SR-002"], "rejected")
    assert code == 0 and no["rejected"] == ["SR-002"]
    code, last, _ = _press(monkeypatch, capsys, repo, by_record["SR-003"], "accepted")
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
    (trial,) = [e for e in events if e.kind == "trial"]
    assert sorted(a["answer"] for a in trial.payload["answers"]) == [
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

    text = (Path(__file__).resolve().parents[2] / "plugin" / "hooks" / "fixtures.ts").read_text(
        encoding="utf-8")
    found = re.search(rf"// BEGIN {name}\n.*?= (.*?)\n// END {name}", text, re.S)
    assert found, name
    return json.loads(found.group(1))


def test_the_panels_trial_fixtures_have_the_shape_of_a_real_trial_draw_and_press(
        batch, repo: Path, monkeypatch, capsys) -> None:
    ids, card = batch
    (fixture,) = _fixture("DRAW_TRIAL")["cards"]
    assert set(fixture) == set(card) and fixture["kind"] == card["kind"] == "trial"
    assert set(fixture["questions"][0]) == set(card["questions"][0])
    assert set(fixture["offers"][0]) == set(card["offers"][0])
    assert [(b["label"], b["answer"]) for b in fixture["offers"][0]["buttons"]] == [
        (b["label"], b["answer"]) for b in card["offers"][0]["buttons"]]
    assert {o["question"] for o in fixture["offers"]} == {q["id"] for q in fixture["questions"]}
    code, pressed, _ = _press(monkeypatch, capsys, repo, card["offers"][1], "rejected")
    shown = _fixture("PRESS_TRIAL_NO")
    assert code == 0 and set(shown) == set(pressed)
    assert (shown["answer"], shown["status"]) == (pressed["answer"], pressed["status"])
    assert shown["line"].split(":")[0] == pressed["line"].split(":")[0]


def test_a_record_answered_in_its_batch_is_not_offered_again(batch, repo: Path, monkeypatch,
                                                              capsys) -> None:
    ids, card = batch
    by_record = {o["record"]: o for o in card["offers"]}
    assert _press(monkeypatch, capsys, repo, by_record["SR-001"], "accepted")[0] == 0
    again = _trial(_draw(monkeypatch, capsys, repo))
    assert again["id"] == card["id"] and again["repeats"] is True
    assert sorted(o["record"] for o in again["offers"]) == ["SR-002", "SR-003"]
    assert sorted(q["record"] for q in again["questions"]) == ["SR-002", "SR-003"]
    # each offer is still the one first drawn for its record
    assert {o["record"]: o["offer_id"] for o in again["offers"]} == {
        r: by_record[r]["offer_id"] for r in ("SR-002", "SR-003")}


def test_the_calibration_waits_for_the_batch_then_counts_every_press(
        batch, repo: Path, monkeypatch, capsys) -> None:
    """SR-106: calibration reruns after each batch; a yes pressed on one record of a batch
    still open does not rerun it (settling cannot switch on from half a batch), and once the
    batch is answered the rerun counts that yes too."""
    ids, card = batch
    by_record = {o["record"]: o for o in card["offers"]}
    assert _press(monkeypatch, capsys, repo, by_record["SR-001"], "accepted")[0] == 0
    _turn_end(repo)
    assert not [e for e in open_core(repo).events() if e.kind == "calibration"]
    assert _press(monkeypatch, capsys, repo, by_record["SR-002"], "accepted")[0] == 0
    assert _press(monkeypatch, capsys, repo, by_record["SR-003"], "accepted")[0] == 0
    _turn_end(repo)
    (calibration,) = [e for e in open_core(repo).events() if e.kind == "calibration"]
    assert calibration.payload["source"] == "logged"
    assert calibration.payload["per_kind"]["example-restatement"]["positives"] == 3


def test_a_batch_left_open_is_not_asked_again_in_a_new_batch(batch, repo: Path, monkeypatch,
                                                             capsys) -> None:
    ids, card = batch
    by_record = {o["record"]: o for o in card["offers"]}
    assert _press(monkeypatch, capsys, repo, by_record["SR-001"], "accepted")[0] == 0
    assert _press(monkeypatch, capsys, repo, by_record["SR-002"], "open")[0] == 0
    _turn_end(repo)
    trials = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "trial"]
    assert [(c.id, c.status) for c in trials] == [(card["id"], "left_open")]
