"""SP8 lane JUDGE, J4: the trial (SR-106, SR-133; SR-042 thresholds per kind)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from understand.test_judge_job import (
    intent_text,
    log_prompt,
    requirement_text,
    verdict_answer,
)

pytestmark = pytest.mark.sr("SR-106")

SESSION = "s1"
MESSAGE = "Build a calculator with add, subtract, multiply, divide, power, root and modulo."


def make_world(repo: Path, write_record, count: int = 3) -> list[str]:
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "Build a calculator", "A calculator", prompt=digest))
    ids = []
    for n in range(1, count + 1):
        write_record(repo, requirement_text(
            n, f"Operation {n}", f"The calculator does operation {n}", intent=1,
            examples=((f"input {n}", "it runs", f"output {n}"),)))
        ids.append(f"SR-{n:03d}")
    return ids


def log_calibration(core: Any, threshold: float = 0.8, passing: bool = True,
                    kind: str = "example-restatement") -> None:
    core.log_append("events", "calibration", {
        "backend": "judge", "model_version": "fake", "source": "logged",
        "per_kind": {kind: {"passing": passing, "threshold": threshold}}})


def apply_scores(core: Any, ids: list[str], scores: list[float]):
    from plumb.understand import judge

    job = judge.build(core, SESSION, records=ids)
    assert job is not None
    return judge.apply(core, job, verdict_answer(
        *((i, "supported", s) for i, s in zip(ids, scores, strict=True))))


def trial_cards(applied: Any) -> list[Any]:
    return [c for c in applied.cards if c.kind == "trial"]


def test_ex1_no_calibration_three_supported_three_cards_nothing_settled(
        repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 3)
    applied = apply_scores(open_core(repo), ids, [0.95, 0.9, 0.97])
    cards = trial_cards(applied)
    assert [c.questions[0].record for c in cards] == ["SR-003", "SR-001", "SR-002"]   # sure first
    assert all(len(c.questions) == 1 for c in cards)                  # one record per card
    assert not [e for e in applied.entries if e["kind"] in ("approval", "settle-config")]
    assert "Build a calculator" in cards[1].evidence and "6 Oct" in cards[1].evidence
    assert cards[1].topic == "Operation 1"


def test_ex7_a_record_below_the_threshold_is_drawn_when_none_open_is(
        repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 6)
    log_calibration(open_core(repo), 0.8)
    applied = apply_scores(open_core(repo), ids, [0.99, 0.97, 0.95, 0.9, 0.85, 0.6])
    assert [c.questions[0].record for c in trial_cards(applied)] == ["SR-006", "SR-001", "SR-002"]


def test_no_more_than_three_cards_are_open(repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 7)
    cards = trial_cards(apply_scores(open_core(repo), ids, [0.99, 0.98, 0.97, 0.96, 0.95, 0.94,
                                                            0.93]))
    assert len(cards) == 3 and len({c.id for c in cards}) == 3


def test_open_cards_and_confirmed_records_are_not_offered_twice(repo: Path,
                                                                  write_record) -> None:
    from plumb.understand import cardstore, trial

    ids = make_world(repo, write_record, 3)
    core = open_core(repo)
    applied = apply_scores(core, ids, [0.95, 0.9, 0.97])
    cardstore.save(repo, SESSION, applied.cards)
    # a second, equal judgment adds no second card for records an open card already holds
    again = trial.cards_for(open_core(repo), SESSION, [])
    assert again == []


def test_ex6_yes_is_a_labelled_yes_and_recalibration_makes_no_model_call(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.approvals import approval_items
    from plumb.capture import calibrate
    from plumb.understand import recheck_words, trial
    from understand.fakes import as_worker

    ids = make_world(repo, write_record, 3)
    core = open_core(repo)
    applied = apply_scores(core, ids, [0.95, 0.9, 0.97])
    card = trial_cards(applied)[0]
    for entry in applied.entries:                      # the worker writes what apply returns
        core.log_append("events", entry["kind"], entry["payload"])
    confirmed: list[tuple[Any, ...]] = []
    done = card.__class__(**{**card.__dict__, "status": "answered", "answers": tuple(
        card.answers) + tuple(_answer(q, "accepted") for q in card.questions)})
    result = trial.effect(core=core, job=None, card=done, question=card.questions[0].id,
                          entry={"answer": "accepted", "record": "SR-001", "hash": "h",
                                 "confidence": 0.9, "evidence": "yes"},
                          message="yes", digest="sha256:0", accepted=True,
                          confirm=lambda *a, **k: confirmed.append(a))
    (log,) = [e for e in result.entries if e["kind"] == "trial"]
    assert log["payload"]["card"] == card.id
    assert [i["id"] for i in log["payload"]["items"]] == ["SR-003"]
    # the yes itself is recorded by the reader as an owner-words approval, label yes
    monkeypatch.setattr(recheck_words, "problem", lambda entry, core: None)
    # the reader logs the owner's message as a prompt event before it writes a confirmation
    # by their words (READ's re-check refuses an approval citing no earlier prompt event)
    core.log_append("events", "prompt", {"digest": "sha256:0", "session": SESSION,
                                         "at": "2026-10-10T10:00:00Z"})
    with as_worker(core.root, SESSION):
        for record_id in ids:
            core.log_append("events", "approval", {
                "records": approval_items(core, [record_id]), "by": "owner-words",
                "label": "yes", "prompt_digest": "sha256:0", "evidence": "yes",
                "job": "read-1", "confidence": 0.9})
    fresh = open_core(repo)
    labelled = [i for i in calibrate.labelled_set(fresh) if i.label == "yes"]
    assert sorted(i.record for i in labelled) == ids and all(i.source == "owner"
                                                             for i in labelled)

    class NoModel:
        name = "disabled"

        def entailment(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("recalibration called a model")

    entry, results = calibrate.calibrate(fresh, backend=NoModel())
    assert entry.payload["source"] == "logged"
    result_kind = results["example-restatement"]
    assert result_kind.positives == 3                  # the logged judge scores were used
    assert not result_kind.passing                     # three decisions are not enough yet


def test_a_card_whose_record_is_confirmed_is_withdrawn_at_turn_end_and_its_slot_frees(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from plumb.understand import cardstore, trial

    ids = make_world(repo, write_record, 4)
    core = open_core(repo)
    applied = apply_scores(core, ids, [0.95, 0.9, 0.97, 0.5])
    for entry in applied.entries:
        core.log_append("events", entry["kind"], entry["payload"])
    cardstore.save(repo, SESSION, trial_cards(applied))
    real = type(core).status

    def status(self: Any, ids: Any = None) -> Any:          # SR-003 was confirmed by a read-back yes
        got = real(self, ids)
        if "SR-003" in got:
            got["SR-003"] = replace(got["SR-003"], confirmation="confirmed")
        return got

    monkeypatch.setattr(type(core), "status", status)
    opened = trial.top_up(open_core(repo), SESSION)
    state = {c.questions[0].record: c.status for c in cardstore.own_cards(repo, SESSION)}
    assert state["SR-003"] == "withdrawn" and state["SR-001"] == "open"
    assert len(opened) == 1 and opened[0].questions[0].record not in state


def _answer(question: Any, said: str) -> Any:
    from plumb.contracts import ClarifyAnswer

    return ClarifyAnswer(question.id, said, "sha256:0")


def test_a_no_answer_closes_the_card_without_confirming(repo: Path, write_record) -> None:
    from plumb.understand import trial

    ids = make_world(repo, write_record, 1)
    applied = apply_scores(open_core(repo), ids, [0.95])
    (card,) = trial_cards(applied)
    done = card.__class__(**{**card.__dict__, "status": "answered",
                             "answers": (_answer(card.questions[0], "rejected"),)})
    called: list[Any] = []
    result = trial.effect(core=open_core(repo), job=None, card=done,
                          question=card.questions[0].id,
                          entry={"answer": "rejected", "record": "SR-001"}, message="no",
                          digest="sha256:0", accepted=False,
                          confirm=lambda *a, **k: called.append(a))
    assert called == []
    (log,) = [e for e in result.entries if e["kind"] == "trial"]
    assert log["payload"]["answers"] == [{"question": card.questions[0].id,
                                          "answer": "rejected"}]


def test_thresholds_are_per_kind_and_start_from_the_config(repo: Path, write_record) -> None:
    from plumb.understand import trial

    make_world(repo, write_record, 1)
    core = open_core(repo)
    assert trial.threshold(core, "requirement") == core.config.understand.reader_threshold_start
    log_calibration(core, 0.7, kind="example-restatement")
    log_calibration(open_core(repo), 0.95, passing=False, kind="intent-readback")
    fresh = open_core(repo)
    assert trial.threshold(fresh, "requirement") == 0.7
    assert trial.threshold(fresh, "intent") == fresh.config.understand.reader_threshold_start
