"""SR-372: the judge approves what does not contradict the owner. JEV is asked whether a record
contradicts the owner's words, adds intent they did not give, or neither (``benign``), never
whether their words entail it; a benign record is approved ``by: auto-jev`` naming the verdict,
only a contradiction or new intent asks the owner one question, and the owner reverses an
approved record by saying so. JEV (a local HTTP stub or a test double) and the model are stubs."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "capture"))
from capture_helpers import JevStub, use_jev  # noqa: E402

from plumb.api import open_core  # noqa: E402
from plumb.understand import judge, read, verdict  # noqa: E402
from understand import test_judge_cascade  # noqa: E402
from understand.fakes import FakeDispatcher, as_worker  # noqa: E402
from understand.test_judge_cascade import StubJev, configure, fast_track_on  # noqa: E402
from understand.test_judge_job import SESSION, build_job, requirement_text  # noqa: E402
from understand.test_judge_questions import answer, asking, written  # noqa: E402

pytestmark = pytest.mark.sr("SR-372")

world = test_judge_cascade.world   # INT-001 and SR-001 from the owner's logged message


class Labelled(StubJev):
    """JEV answering ``label`` on the approval question, with ``p`` the probability of benign."""

    def __init__(self, label: str, p: float) -> None:
        super().__init__(p)
        self.label = label

    def approval(self, premise: str, hypothesis: str, *, subject: str, claim_kind: str) -> Any:
        found = super().approval(premise, hypothesis, subject=subject, claim_kind=claim_kind)
        return dataclasses.replace(found, verdict=self.label)


def switch_on(core: Any) -> None:
    core.log_append("events", "config", {"by": "owner", "auto_approve": {
        "enabled": True, "backend": "jev", "min_probability": 0.9, "min_confidence": "high"}})


def judged(core: Any, ids: list[str], jev: Any, model: FakeDispatcher) -> Any:
    job = build_job(core, ids)
    done = verdict.cascade(core, job, system="judge", schema={}, jev=jev, dispatcher=model)
    return judge.apply(core, job, done.answer)


def write(repo: Path, applied: Any) -> None:
    core = open_core(repo)
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])


def approvals(applied: Any) -> list[dict[str, Any]]:
    return [e["payload"] for e in applied.entries if e["kind"] == "approval"]


def test_ex1_a_restating_requirement_is_judge_approved_with_no_question(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = JevStub()                                    # JEV: benign, 0.95
    use_jev(world, stub, monkeypatch)
    core = open_core(world)
    switch_on(core)
    model = FakeDispatcher()
    applied = judged(core, ["SR-001"], verdict.open_jev(core), model)
    asked = [q for request in stub.requests for q in request["questions"].values()]
    assert asked and all(q["type"] == "choice" and list(q["criteria"]) == [
        "benign", "extends", "contradicts"] for q in asked)      # never the entailment form
    [approval] = approvals(applied)
    assert approval["by"] == "auto-jev" and approval["auto"]["verdict"] == "benign"
    assert model.jobs == [] and written(world) == []             # no question asked
    write(world, applied)
    status = open_core(world).status(["SR-001"])["SR-001"]
    assert (status.confirmation, status.approved_by) == ("confirmed", "auto-jev")
    stub.close()


def test_ex2_a_benign_extension_is_judge_approved_and_marked_benign(
        world: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    write_record(world, requirement_text(
        1, "Pages load in two seconds", "Public pages load within two seconds", intent=1,
        examples=(("a public page", "it is requested", "it loads within 2 seconds"),
                  ("a public page with a cold cache", "it is requested",
                   "it still loads within 2 seconds"))))     # an edge case the owner never named
    core = configure(world)
    fast_track_on(core, monkeypatch)
    model = FakeDispatcher()
    applied = judged(core, ["SR-001"], Labelled("benign", 0.96), model)
    [approval] = approvals(applied)
    assert approval["by"] == "auto-jev" and approval["auto"]["verdict"] == "benign"
    logged = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    assert logged["jev_verdict"] == "benign" and model.jobs == []
    write(world, applied)
    assert open_core(world).status(["SR-001"])["SR-001"].approved_by == "auto-jev"


def test_ex3_a_reversal_of_confirmed_behaviour_asks_one_question(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core = configure(world)
    fast_track_on(core, monkeypatch)
    model = FakeDispatcher({"judge": answer(
        ("SR-001", "contradicts"), questions=[asking("SR-001")],
        **{"SR-001": {"contradicts": ["pages load faster"]}})})
    applied = judged(core, ["SR-001"], Labelled("contradicts", 0.02), model)
    assert approvals(applied) == [] and len(model.jobs) == 1
    (question,) = written(world)
    assert "load faster" in question["question"].lower()        # the behaviour, plain words
    assert [r["id"] for r in question["records"]] == ["SR-001"]


def test_ex4_a_feature_the_owner_never_asked_for_asks_whether_it_is_theirs(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core = configure(world)
    fast_track_on(core, monkeypatch)
    model = FakeDispatcher({"judge": answer(
        ("SR-001", "beyond"), questions=[asking("SR-001")],
        **{"SR-001": {"beyond": ["a page-speed dashboard"]}})})
    applied = judged(core, ["SR-001"], Labelled("extends", 0.2), model)
    logged = next(e["payload"] for e in applied.entries if e["kind"] == "verdict")
    assert logged["jev_verdict"] == "extends" and not logged["jev_clears"]
    assert approvals(applied) == []
    assert len(written(world)) == 1


def test_a_record_that_contradicts_nothing_is_never_asked_about(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing else asks: the judge model finds the record supported and still sends a
    question; it is not put to the owner, and the record waits for JEV."""
    core = configure(world)
    model = FakeDispatcher({"judge": answer(("SR-001", "supported"),
                                            questions=[asking("SR-001")])})
    applied = judged(core, ["SR-001"], None, model)
    assert approvals(applied) == [] and written(world) == []
    assert any("contradicts nothing" in n for n in applied.notes)


def test_ex6_the_owner_saying_an_approved_record_is_wrong_reverses_it(
        world: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from understand.test_read_job import log_prompt, state

    core = configure(world)
    fast_track_on(core, monkeypatch)
    write(world, judged(core, ["SR-001"], Labelled("benign", 0.96), FakeDispatcher()))
    core = open_core(world)
    assert core.status(["SR-001"])["SR-001"].approved_by == "auto-jev"
    state(core, ["SR-001"])
    said = "No, the two-second rule is wrong, I never wanted a fixed limit."
    digest = log_prompt(core, said)
    job = read.build(core, SESSION, message={"digest": digest, "text": said})
    assert job is not None
    evidence = "the two-second rule is wrong"
    with as_worker(world, SESSION):
        applied = read.apply(core, job, {"entries": [{
            "id": "SR-001", "hash": core.index()["SR-001"].hash, "answer": "rejected",
            "evidence": evidence, "confidence": 0.95}]})
    write(world, applied)
    core = open_core(world)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    [reversal] = [e.payload for e in core.events() if e.kind == "revocation"]
    assert reversal["by"] == "owner-words" and reversal["reason"] == evidence
