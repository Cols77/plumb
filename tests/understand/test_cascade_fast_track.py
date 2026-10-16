"""One cascade (task 1 of the judge-approval plan): capture only queues the judge job, JEV scores
every record there, calibrated or not, and a record JEV clears strictly above max(0.9, the
calibrated threshold) is approved ``by: auto-jev`` in the judge job when the owner's fast track
is in effect; every other record goes to the judge model. JEV and the model are stubs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "capture"))
from plumb.api import open_core  # noqa: E402
from plumb.understand import judge, verdict  # noqa: E402
from understand import test_judge_cascade  # noqa: E402
from understand.fakes import FakeDispatcher, as_worker  # noqa: E402
from understand.test_judge_cascade import (  # noqa: E402
    StubJev,
    calibrate_to,
    configure,
    fast_track_on,
)
from understand.test_judge_job import (  # noqa: E402
    SESSION,
    approve,
    build_job,
    intent_text,
    log_prompt,
    requirement_text,
    verdict_answer,
)

world = test_judge_cascade.world   # the shared fixture


class Versioned(StubJev):
    """A JEV stub resolving ``version`` and answering ``scores[subject]`` (else ``default``)."""

    def __init__(self, default: float, scores: dict[str, float] | None = None,
                 version: str = "jev-1") -> None:
        super().__init__(default)
        self.default, self.scores, self.version = default, scores or {}, version

    def entailment(self, premise: str, hypothesis: str, *, subject: str, claim_kind: str) -> Any:
        self.probability = self.scores.get(subject, self.default)
        judgment = super().entailment(premise, hypothesis, subject=subject,
                                      claim_kind=claim_kind)
        from dataclasses import replace

        return replace(judgment, backend=f"jev:{self.version}")


def judged(core: Any, ids: list[str], jev: Any, model: FakeDispatcher | None = None
           ) -> tuple[Any, Any, Any]:
    """``(job, cascaded, applied)`` of one judge job over ``ids``."""
    job = build_job(core, ids)
    done = verdict.cascade(core, job, system="judge", schema={}, jev=jev,
                           dispatcher=model or FakeDispatcher())
    return job, done, judge.apply(core, job, done.answer)


def write(repo: Path, applied: Any) -> None:
    core = open_core(repo)
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])


def approvals(applied: Any) -> list[dict[str, Any]]:
    return [e["payload"] for e in applied.entries if e["kind"] == "approval"]


def verdict_of(applied: Any, record_id: str) -> dict[str, Any]:
    return next(e["payload"] for e in applied.entries
                if e["kind"] == "verdict" and e["payload"]["id"] == record_id)


def model_for(*ids: str) -> FakeDispatcher:
    return FakeDispatcher({"judge": verdict_answer(*((i, "supported", 0.8) for i in ids))})


def asked(model: FakeDispatcher) -> list[str]:
    return [r["id"] for job in model.jobs for r in job.inputs["records"]]


# ---- SR-248 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-248")
def test_ex1_an_intent_jev_scores_above_the_threshold_is_approved_without_a_question(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-1: fast track on, threshold 0.93, JEV 0.96: approved by auto-jev, no question."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    model = FakeDispatcher()
    _, _, applied = judged(core, ["INT-001"], StubJev(0.96), model)
    [approval] = approvals(applied)
    assert approval["by"] == "auto-jev" and approval["auto"]["score"] == 0.96
    assert approval["session"] == SESSION and model.jobs == []          # no question asked
    write(world, applied)
    status = open_core(world).status(["INT-001"])["INT-001"]
    assert (status.confirmation, status.approved_by) == ("confirmed", "auto-jev")


@pytest.mark.sr("SR-248")
def test_ex3_a_score_above_0_9_but_below_the_threshold_goes_to_the_judge_model(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-3: threshold 0.93, JEV 0.92: not fast-tracked, the judge model is asked."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    model = model_for("SR-001")
    _, _, applied = judged(core, ["SR-001"], StubJev(0.92), model)
    assert approvals(applied) == [] and asked(model) == ["SR-001"]
    assert verdict_of(applied, "SR-001")["jev_score"] == 0.92


@pytest.mark.sr("SR-248")
def test_ex6_a_quote_only_premise_is_never_fast_tracked(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-6: the premise is a message the agent recorded itself, JEV 0.97: logged
    quote-only, the judge model is asked."""
    said = "Keep the checkout plain, the shop is small."
    digest = "sha256:" + __import__("hashlib").sha256(said.encode("utf-8")).hexdigest()
    path = repo / ".plumb" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"digest": digest, "session": SESSION, "via": "turn",
                                "at": "2026-10-06T10:00:00Z", "text": said}) + "\n",
                    encoding="utf-8")
    write_record(repo, intent_text(1, "Keep the checkout plain", "A plain checkout",
                                   prompt=digest))
    core = configure(repo)
    fast_track_on(core, monkeypatch)
    model = model_for("INT-001")
    _, _, applied = judged(core, ["INT-001"], StubJev(0.97), model)
    logged = verdict_of(applied, "INT-001")
    assert logged["premise"] == "quote-only" and logged["jev_score"] == 0.97
    assert approvals(applied) == [] and asked(model) == ["INT-001"]


@pytest.mark.sr("SR-248")
def test_ex9_an_edit_of_a_record_the_owner_confirmed_is_never_fast_tracked(
        world: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-248 EX-9: the agent edits a requirement the owner confirmed, JEV 0.97: it stays an
    unconfirmed edit and goes to the judge model."""
    core = configure(world)
    approve(core, "SR-001")
    write_record(world, requirement_text(
        1, "Pages load in one second", "Public pages load within one second", intent=1,
        examples=(("a public page", "it is requested", "it loads within 1 second"),)))
    core = open_core(world)
    assert core.status(["SR-001"])["SR-001"].confirmation == "unconfirmed-edit"
    fast_track_on(core, monkeypatch)
    model = model_for("SR-001")
    _, _, applied = judged(core, ["SR-001"], StubJev(0.97), model)
    assert approvals(applied) == [] and asked(model) == ["SR-001"]
    write(world, applied)
    assert open_core(world).status(["SR-001"])["SR-001"].confirmation == "unconfirmed-edit"


# ---- SR-242 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-242")
def test_ex1_jev_above_its_threshold_stands_and_the_model_is_not_called(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-242 EX-1: JEV 0.95, threshold 0.43: supported on JEV, the model is not called, the
    fast track uses it."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.43)
    model = FakeDispatcher()
    _, done, applied = judged(core, ["INT-001"], StubJev(0.95), model)
    [v] = done.answer["verdicts"]
    assert (v["verdict"], v["by"]) == ("supported", "jev") and model.jobs == []
    assert [a["by"] for a in approvals(applied)] == ["auto-jev"]


@pytest.mark.sr("SR-242")
def test_ex2_jev_low_on_a_requirement_the_model_judges_with_its_name(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-242 EX-2: JEV 0.3 on a requirement's examples: the judge model judges it, logged
    with its name; no fast track on JEV."""
    core = configure(world)
    fast_track_on(core, monkeypatch)
    model = FakeDispatcher({"judge": verdict_answer(("SR-001", "beyond", 0.8))})
    _, _, applied = judged(core, ["SR-001"], StubJev(0.3), model)
    logged = verdict_of(applied, "SR-001")
    assert (logged["by"], logged["model"]) == ("model", "haiku")
    assert logged["judge"].endswith(":haiku") and logged["jev_score"] == 0.3
    assert approvals(applied) == []


@pytest.mark.sr("SR-242")
def test_ex5_a_probability_equal_to_the_threshold_goes_to_the_model(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-242 EX-5: JEV equals the calibrated 0.93 exactly: the judge model judges it, and an
    auto-jev approval at that score fails its re-check."""
    core = configure(world)
    fast_track_on(core, monkeypatch, 0.93)
    model = model_for("INT-001")
    _, _, applied = judged(core, ["INT-001"], StubJev(0.93), model)
    assert approvals(applied) == [] and asked(model) == ["INT-001"]
    from plumb.capture.autoapprove import recheck

    calibration = [e for e in core.events() if e.kind == "calibration"][-1]
    entry = type("E", (), {"payload": {
        "records": [{"id": "INT-001"}], "by": "auto-jev", "prompt_digest": "p",
        "auto": {"score": 0.93, "calibration": calibration.digest, "model_version": "jev-1",
                 "claim_kind": "intent-readback", "judge": "jev", "prompt_via": "hook",
                 "confidence_label": "high"}}})()
    problem = recheck(entry, {"enabled": True, "min_probability": 0.9},
                      {calibration.digest: calibration}, {"p"}, set())
    assert problem is not None and "not above the threshold 0.930" in problem


# ---- SR-250 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-250")
def test_ex4_config_yaml_on_without_the_owners_event_is_not_the_fast_track(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-250 EX-4: config.yaml says enabled, no owner switch event, JEV 0.97: not fast-tracked,
    the judge model is asked, validate warns about the mismatch."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    core = configure(world, "auto_approve: {enabled: true}\n")
    calibrate_to(core, 0.5)
    model = model_for("INT-001")
    _, _, applied = judged(core, ["INT-001"], StubJev(0.97), model)
    assert approvals(applied) == [] and asked(model) == ["INT-001"]
    from plumb.validate import validate

    assert any(f.code == "auto-approve-mirror" and f.severity == "warning"
               for f in validate(open_core(world)))


@pytest.mark.sr("SR-250")
def test_ex7_the_agent_editing_config_yaml_never_switches_the_fast_track_on(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-250 EX-7: the owner switched it off; the agent writes enabled true in config.yaml:
    the next record judged does not take the fast track."""
    core = configure(world)
    fast_track_on(core, monkeypatch)
    core.log_append("events", "config", {"by": "owner", "auto_approve": {"enabled": False}})
    config = world / ".plumb" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "auto_approve: {enabled: true}\n",
                      encoding="utf-8")
    core = open_core(world)
    model = model_for("INT-001")
    _, _, applied = judged(core, ["INT-001"], StubJev(0.97), model)
    assert approvals(applied) == [] and asked(model) == ["INT-001"]


@pytest.fixture
def owner_on(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch):
    """The real JEV client against a local stub, calibrated, the owner's switch on, and one
    intent from a message the prompt hook logged."""
    from capture_helpers import run
    from jev_fixtures import calibrated

    stub = calibrated(repo, write_record, monkeypatch)
    assert run(repo, "config", "auto-approve", "on") == 0   # the owner's terminal (test)
    said = "I want pages to load faster."
    write_record(repo, intent_text(1, "I want pages to load faster", "Make pages load faster",
                                   prompt=log_prompt(repo, said)))
    yield repo, stub
    stub.close()


@pytest.mark.sr("SR-250")
def test_ex5_a_new_jev_version_suspends_the_fast_track(owner_on: Any) -> None:
    """SR-250 EX-5: JEV now resolves jev-1.14: nothing is fast-tracked and the status says
    the fast track waits for a new calibration."""
    from plumb.capture.autoapprove import auto_approve_state, state_line

    repo, stub = owner_on
    stub.model = "jev-1.14.0"
    core = open_core(repo)
    model = model_for("INT-001")
    _, _, applied = judged(core, ["INT-001"], verdict.open_jev(core), model)
    assert approvals(applied) == [] and asked(model) == ["INT-001"]
    state = auto_approve_state(open_core(repo))
    assert state.suspended and not state.effective
    line = state_line(state)
    assert "suspended" in line and "calibrate" in line


@pytest.mark.sr("SR-250")
def test_ex6_a_dated_name_of_the_same_version_keeps_the_fast_track(owner_on: Any) -> None:
    """SR-250 EX-6: calibrated on jev-1.13.0, JEV resolves typesafe/jev-1.13-20260917: the
    fast track stays on and the intent is approved."""
    repo, stub = owner_on
    stub.model = "typesafe/jev-1.13-20260917"
    core = open_core(repo)
    model = FakeDispatcher()
    _, _, applied = judged(core, ["INT-001"], verdict.open_jev(core), model)
    assert [a["by"] for a in approvals(applied)] == ["auto-jev"] and model.jobs == []


# ---- SR-245 -------------------------------------------------------------------------------


@pytest.mark.sr("SR-245")
def test_ex3_the_judges_key_missing_holds_the_approval_with_one_line(
        world: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SR-245 EX-3: the switch on, JEV's key missing: one line says the judge is unreachable,
    nothing is approved by rule; said once."""
    from plumb.judgment import jev as jev_mod

    core = configure(world)
    fast_track_on(core, monkeypatch)
    monkeypatch.delenv("TYPESAFE_API_KEY")
    monkeypatch.setattr(jev_mod, "user_config_path", lambda: tmp_path / "none.json")
    monkeypatch.setattr(jev_mod, "user_store_path", lambda: tmp_path / "none")
    core = open_core(world)
    job = build_job(core, ["INT-001"])
    model = model_for("INT-001")
    done = verdict.cascade(core, job, system="judge", schema={}, dispatcher=model)
    lines = done.line.splitlines()
    assert len(lines) == 1 and "auto-approval is waiting" in lines[0]
    assert "TYPESAFE_API_KEY" in lines[0]
    assert approvals(judge.apply(core, job, done.answer)) == []
    again = verdict.cascade(core, job, system="judge", schema={}, dispatcher=model)
    assert again.line == ""


@pytest.mark.sr("SR-245")
def test_ex6_two_cleared_by_jev_are_applied_and_three_wait_for_the_model(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-245 EX-6: a job of five records, JEV clears two, the judge model is unreachable: the
    two are applied as JEV's, the three others wait, one line says so."""
    said = "I want pages to load faster and a dashboard of the load times."
    write_record(repo, intent_text(1, "I want pages to load faster", "Make pages load faster",
                                   prompt=log_prompt(repo, said)))
    for n in range(1, 5):
        write_record(repo, requirement_text(n, f"Load rule {n}", f"Pages follow rule {n}",
                                            intent=1))
    core = configure(repo)
    fast_track_on(core, monkeypatch)
    ids = ["INT-001", "SR-001", "SR-002", "SR-003", "SR-004"]
    jev = Versioned(0.2, {"INT-001": 0.97, "SR-001": 0.97})
    job, done, applied = judged(core, ids, jev, FakeDispatcher(reason="no model answered"))
    assert sorted(v["id"] for v in done.answer["verdicts"]) == ["INT-001", "SR-001"]
    assert all(v["by"] == "jev" for v in done.answer["verdicts"])
    assert [e["id"] for e in done.left] == ["SR-002", "SR-003", "SR-004"]
    assert len(done.line.splitlines()) == 1 and "no model answered" in done.line
    assert sorted(a["records"][0]["id"] for a in approvals(applied)) == ["INT-001", "SR-001"]


# ---- the rest of the task ------------------------------------------------------------------


@pytest.mark.sr("SR-248")
def test_without_a_calibration_jev_is_asked_its_score_logged_and_the_model_judges(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No calibration: JEV is asked, ``jev_score`` logged, nothing fast-tracked, the record
    goes to the model."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    core = configure(world)
    core.log_append("events", "config", {"by": "owner", "auto_approve": {"enabled": True}})
    jev, model = StubJev(0.99), model_for("INT-001")
    _, _, applied = judged(core, ["INT-001"], jev, model)
    assert jev.calls == [("INT-001", "intent-readback")]
    logged = verdict_of(applied, "INT-001")
    assert logged["jev_score"] == 0.99 and logged["jev_clears"] is False
    assert logged["by"] == "model" and asked(model) == ["INT-001"]
    assert approvals(applied) == []


@pytest.mark.sr("SR-210")
@pytest.mark.parametrize("kind,payload", [
    ("approval", {"by": "auto-jev", "records": [{"id": "INT-001", "hash": "sha256:0"}]}),
    ("pre-intent", {"source": "sha256:0", "text": "yes"}),
])
def test_an_auto_jev_or_pre_intent_entry_needs_the_workers_token(
        world: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
        payload: dict[str, Any]) -> None:
    """An ``auto-jev`` approval or a ``pre-intent`` written without the worker token is
    refused; the worker writes it."""
    from plumb.log import LogError

    monkeypatch.delenv("PLUMB_WORKER", raising=False)
    core = open_core(world)
    with pytest.raises(LogError, match="worker only"):
        core.log_append("events", kind, {**payload, "session": SESSION})
    with as_worker(world, SESSION):
        core.log_append("events", kind, {**payload, "session": SESSION})
    assert [e.kind for e in open_core(world).events()].count(kind) == 1
