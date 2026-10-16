"""SR-182: the verdict is a cascade. JEV first (its probability strictly above max(0.9, the
calibrated zero-false-accept threshold), with the fast track on, makes the verdict JEV's and
approves the record); below it, or without JEV, the judge model (understand.judge_model) gives a
verdict marked as the model's that never takes the fast track; with neither reachable the
verdict waits and the step says so once. JEV and the model are stubs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.contracts import Judgment
from understand.fakes import FakeDispatcher
from understand.test_judge_job import (
    MESSAGE,
    SESSION,
    build_job,
    intent_text,
    log_prompt,
    requirement_text,
    verdict_answer,
)

pytestmark = pytest.mark.sr("SR-242")

THRESHOLD = 0.43


class StubJev:
    """A JEV backend that answers one probability for every claim."""

    name = "jev"
    version = "jev-1"

    def __init__(self, probability: float) -> None:
        self.probability = probability
        self.calls: list[tuple[str, str]] = []

    def entailment(self, premise: str, hypothesis: str, *, subject: str,
                   claim_kind: str) -> Judgment:
        self.calls.append((subject, claim_kind))
        p = self.probability
        return Judgment(action="faithfulness", subject=subject,
                        verdict="entailed" if p >= 0.5 else "not-entailed",
                        confidence=p, tier="accept", backend="jev:jev-1", fingerprint="f",
                        reasons=(), probability=p, confidence_label="high")


@pytest.fixture
def world(repo: Path, write_record):
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, "I want pages to load faster", "Make pages load faster",
                                   prompt=digest, will=("Pages load faster",)))
    write_record(repo, requirement_text(
        1, "Pages load in two seconds", "Public pages load within two seconds", intent=1,
        examples=(("a public page", "it is requested", "it loads within 2 seconds"),)))
    return repo


def calibrate_to(core: Any, threshold: float = THRESHOLD) -> None:
    kind = {"threshold": threshold, "passing": True}
    core.log_append("events", "calibration", {
        "backend": "jev", "model_version": "jev-1",
        "per_kind": {"intent-readback": dict(kind), "example-restatement": dict(kind)}})


def fast_track_on(core: Any, monkeypatch: pytest.MonkeyPatch,
                  threshold: float = THRESHOLD) -> None:
    """JEV's key present, a passing calibration at ``threshold`` and the owner's switch on."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    calibrate_to(core, threshold)
    core.log_append("events", "config", {"by": "owner", "auto_approve": {
        "enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}})


def configure(repo: Path, extra: str = "") -> Any:
    (repo / ".plumb" / "config.yaml").write_text(
        "judgment:\n  backend: jev\n" + extra, encoding="utf-8")
    return open_core(repo)


def run(core: Any, ids: list[str], *, jev: Any, model: FakeDispatcher):
    from plumb.understand import verdict

    job = build_job(core, ids)
    return job, verdict.cascade(core, job, system="judge", schema={}, jev=jev,
                                dispatcher=model)


def by_id(cascaded: Any) -> dict[str, dict[str, Any]]:
    return {v["id"]: v for v in cascaded.answer["verdicts"]}


def test_ex1_jev_above_the_threshold_gives_the_verdict_and_the_model_is_not_asked(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core = configure(world)
    fast_track_on(core, monkeypatch)
    jev, model = StubJev(0.95), FakeDispatcher()
    job, cascaded = run(core, ["INT-001"], jev=jev, model=model)
    v = by_id(cascaded)["INT-001"]
    assert (v["verdict"], v["by"], v["confidence"]) == ("supported", "jev", 0.95)
    assert v["judge"].startswith("jev:")
    assert model.jobs == []                                  # the model was not called
    from plumb.judgment.verdict import refusal

    assert refusal(v["by"], v["verdict"]) is None            # the fast track may use it
    from plumb.understand import judge

    approvals = [e["payload"] for e in judge.apply(core, job, cascaded.answer).entries
                 if e["kind"] == "approval"]
    assert [(a["by"], a["auto"]["score"]) for a in approvals] == [("auto-jev", 0.95)]


def test_ex2_jev_below_the_threshold_sends_the_record_to_the_model(world: Path) -> None:
    core = configure(world)
    calibrate_to(core)
    core.log_append("events", "config", {"by": "owner", "auto_approve": {   # the owner's switch
        "enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}})
    model = FakeDispatcher({"judge": verdict_answer(("SR-001", "supported", 0.97))})
    job, cascaded = run(core, ["SR-001"], jev=StubJev(0.3), model=model)
    v = by_id(cascaded)["SR-001"]
    assert (v["verdict"], v["by"]) == ("supported", "model")
    assert len(model.jobs) == 1
    assert v["jev"]["score"] == 0.3 and not v["jev"]["clears"]
    # the verdict is logged with who gave it, and cards and the tidy job get it as before
    from plumb.understand import judge

    applied = judge.apply(core, job, cascaded.answer)
    logged = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    assert logged["by"] == "model" and logged["verdict"] == "supported"
    assert logged["jev_score"] == 0.3                       # JEV's score is logged
    assert [e for e in applied.entries if e["kind"] == "approval"] == []   # a question first
    assert applied.cards == ()                                            # and no card
    # and auto-approval refuses it in code, however sure the model was
    from plumb.capture.autoapprove import verdict_refusal

    assert "never takes the fast track" in (verdict_refusal(logged) or "")


def test_a_jev_verdict_in_the_log_is_not_refused_by_auto_approval(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core = configure(world)
    fast_track_on(core, monkeypatch)
    job, cascaded = run(core, ["INT-001"], jev=StubJev(0.95), model=FakeDispatcher())
    from plumb.capture.autoapprove import verdict_refusal
    from plumb.understand import judge

    applied = judge.apply(core, job, cascaded.answer)
    logged = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    assert logged["by"] == "jev" and verdict_refusal(logged) is None


def test_a_verdict_with_no_marker_is_not_taken_as_jevs() -> None:
    from plumb.capture.autoapprove import verdict_refusal

    assert verdict_refusal({"verdict": "supported"}) is not None
    assert verdict_refusal({"verdict": "beyond", "by": "jev"}) is not None


def test_ex3_judge_model_setting_picks_the_model_that_judges(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core = configure(world, "understand:\n  judge_model: sonnet\n")
    assert core.config.understand.judge_model == "sonnet"
    calibrate_to(core)
    asked: list[str | None] = []
    fake = FakeDispatcher({"judge": verdict_answer(("SR-001", "supported", 0.9))})

    def configured(core: Any, *, model: str | None = None) -> FakeDispatcher:
        asked.append(model)
        return fake

    monkeypatch.setattr("plumb.understand.dispatch.configured", configured)
    from plumb.understand import judge, verdict

    job = build_job(core, ["SR-001"])
    cascaded = verdict.cascade(core, job, system="judge", schema={}, jev=StubJev(0.1))
    assert asked == ["sonnet"]
    v = by_id(cascaded)["SR-001"]
    assert v["model"] == "sonnet" and v["by"] == "model"
    logged = next(e["payload"] for e in judge.apply(core, job, cascaded.answer).entries
                  if e["kind"] == "verdict")
    assert logged["model"] == "sonnet"          # logged with the model's name


def test_judge_model_is_haiku_by_default(world: Path) -> None:
    assert open_core(world).config.understand.judge_model == "haiku"


def test_without_jev_the_model_judges(world: Path) -> None:
    core = configure(world)
    model = FakeDispatcher({"judge": verdict_answer(("INT-001", "beyond", 0.8))})
    _, cascaded = run(core, ["INT-001"], jev=None, model=model)
    assert by_id(cascaded)["INT-001"]["by"] == "model"


def test_a_jev_that_cannot_answer_sends_the_record_to_the_model(world: Path) -> None:
    from plumb.judgment import JudgmentUnavailable

    class Down(StubJev):
        def entailment(self, *a: Any, **k: Any) -> Judgment:
            raise JudgmentUnavailable("JEV", "timeout")

    core = configure(world)
    calibrate_to(core)
    model = FakeDispatcher({"judge": verdict_answer(("INT-001", "supported", 0.9))})
    _, cascaded = run(core, ["INT-001"], jev=Down(0), model=model)
    assert by_id(cascaded)["INT-001"]["by"] == "model"


def test_without_a_calibration_jev_clears_on_the_floor_but_the_switch_is_off(
        world: Path) -> None:
    """DEC-143: no calibration: JEV clears above 0.9; the owner never switched the fast
    track on, so the model still gives the verdict."""
    core = configure(world)
    model = FakeDispatcher({"judge": verdict_answer(("INT-001", "supported", 0.9))})
    jev = StubJev(0.99)
    _, cascaded = run(core, ["INT-001"], jev=jev, model=model)
    v = by_id(cascaded)["INT-001"]
    assert v["by"] == "model" and jev.calls == [("INT-001", "intent-readback")]
    assert v["jev"]["score"] == 0.99 and v["jev"]["clears"] and v["jev"]["threshold"] == 0.9


def test_ex4_neither_reachable_the_verdict_waits_and_says_so_once(world: Path) -> None:
    from plumb.understand import verdict

    core = configure(world)
    calibrate_to(core)
    model = FakeDispatcher(reason="no model answered")
    job = build_job(core, ["INT-001"])
    with pytest.raises(verdict.Waiting) as first:
        verdict.cascade(core, job, system="judge", schema={}, jev=None, dispatcher=model)
    assert "is waiting" in first.value.line
    with pytest.raises(verdict.Waiting) as second:
        verdict.cascade(core, job, system="judge", schema={}, jev=None, dispatcher=model)
    assert second.value.line == ""                      # said once
    assert model.jobs == []                             # nothing was decided by rule
    assert [e for e in core.events() if e.kind == "verdict"] == []


def test_the_worker_runs_the_cascade_and_logs_which_judge_answered(
        world: Path, engine_standins, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import queue, verdict, worker

    core = configure(world)
    fast_track_on(core, monkeypatch)
    monkeypatch.setattr(verdict, "open_jev", lambda core: StubJev(0.95))
    engine_standins.dispatcher.script = {"judge": verdict_answer(("SR-001", "supported", 0.9))}
    queue.enqueue(core, build_job(core, ["INT-001", "SR-001"]))
    assert worker.run_once(open_core(world), SESSION)
    logged = {e.payload["id"]: e.payload for e in open_core(world).events()
              if e.kind == "verdict"}
    assert logged["INT-001"]["by"] == "jev" and logged["SR-001"]["by"] == "jev"
    statuses = open_core(world).status(["INT-001", "SR-001"])     # the worker approved them
    assert {s.confirmation for s in statuses.values()} == {"confirmed"}
