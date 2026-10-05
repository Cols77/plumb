"""BRIDGE B2: the extracted judgment model and tier routing (spec 8.2)."""

from __future__ import annotations

import dataclasses

import pytest

from plumb.judgment.model import (
    JudgmentAnswer,
    JudgmentQuestion,
    JudgmentRequest,
    make_record,
    verify_record,
)
from plumb.judgment.tiers import Thresholds, route

pytestmark = pytest.mark.sr("SR-021")

T = Thresholds(accept=0.9, escalate_llm=0.5)


def test_route_thresholds() -> None:
    assert route(0.95, T) == "accept"
    assert route(0.9, T) == "accept"
    assert route(0.89, T) == "escalate-llm"
    assert route(0.5, T) == "escalate-llm"
    assert route(0.49, T) == "escalate-human"


def test_version_drift_suspends_accept() -> None:
    assert route(0.95, T, resolved_version="jev-1.13.0",
                 validated_against="jev-1.13.0") == "accept"
    assert route(0.95, T, resolved_version="jev-1.14.0",
                 validated_against="jev-1.13.0") == "escalate-llm"
    # drift never lowers a tier below escalate-llm, nor raises escalate-human
    assert route(0.2, T, resolved_version="jev-1.14.0",
                 validated_against="jev-1.13.0") == "escalate-human"


def test_question_limits_and_wire_shape() -> None:
    q = JudgmentQuestion.noul("Does it change?", "yes", "no")
    assert q.to_wire() == {"type": "noul", "instructions": "Does it change?",
                           "criteria": {"true": "yes", "false": "no"}}
    s = JudgmentQuestion.score("Fit?", ["drifts", "unsure", "fits"])
    assert s.to_wire()["criteria"] == ["drifts", "unsure", "fits"]
    with pytest.raises(ValueError):
        JudgmentQuestion.score("x", ["only"])
    with pytest.raises(ValueError):
        JudgmentQuestion.choice("x", {})


def test_noul_answer_derives_confidence() -> None:
    a = JudgmentAnswer.from_noul(0.2)
    assert a.confidence == pytest.approx(0.8)
    assert a.confidence_source == "derived"
    assert a.probabilities == {"true": 0.2, "false": pytest.approx(0.8)}
    with pytest.raises(ValueError):
        JudgmentAnswer.from_noul(1.5)


def test_record_digest_detects_mutation() -> None:
    request = JudgmentRequest(state="s", questions=(("q", JudgmentQuestion.noul("i", "t",
                                                                               "f")),))
    record = make_record(request, outcome="ok", timestamp="2026-10-06T00:00:00Z",
                         resolved_version="jev-1.13.0",
                         answers={"q": JudgmentAnswer.from_noul(0.9)})
    assert verify_record(record)
    tampered = dataclasses.replace(record, outcome="invalid")
    assert not verify_record(tampered)
    refingered = dataclasses.replace(record, resolved_version="jev-9")
    assert not verify_record(refingered)
