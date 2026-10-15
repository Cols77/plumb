"""SR-185: when the verdict cascade answers some records of a judge job and cannot answer the
rest (model unreachable, request too large, answer out of schema), the verdicts it has are
applied at once, the rest wait as a job of their own, and one line says so once. JEV and the
model are stubs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from understand.fakes import FakeDispatcher
from understand.test_judge_cascade import StubJev, calibrate_to, configure, world  # noqa: F401
from understand.test_judge_job import SESSION, build_job, verdict_answer

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-185")


class ClearsIntent(StubJev):
    """JEV clears the intent and nothing else."""

    def __init__(self) -> None:
        super().__init__(0.9)

    def entailment(self, premise: str, hypothesis: str, *, subject: str, claim_kind: str) -> Any:
        self.probability = 0.9 if subject.startswith("INT") else 0.1
        return super().entailment(premise, hypothesis, subject=subject, claim_kind=claim_kind)


def cascade(core: Any, model: FakeDispatcher, jev: Any = None) -> Any:
    from plumb.understand import verdict

    job = build_job(core, ["INT-001", "SR-001"])
    return verdict.cascade(core, job, system="judge", schema={}, jev=jev, dispatcher=model)


def partly(world: Path, model: FakeDispatcher) -> Any:
    core = configure(world)
    calibrate_to(core)
    return core, cascade(core, model, ClearsIntent())


def test_ex1_jev_clears_one_and_the_unreachable_model_leaves_the_other(world: Path) -> None:
    core, done = partly(world, FakeDispatcher(reason="no model answered"))
    assert [v["id"] for v in done.answer["verdicts"]] == ["INT-001"]
    assert [e["id"] for e in done.left] == ["SR-001"]
    assert "is waiting" in done.line and "SR-001" in done.line and "no model answered" in done.line


def test_ex1_the_worker_logs_the_verdict_keeps_the_rest_and_says_it_to_the_agent(
        world: Path, engine_standins: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    core = configure(world)
    calibrate_to(core)
    from plumb.understand import jobs, queue, verdict, worker

    monkeypatch.setattr(verdict, "open_jev", lambda core: ClearsIntent())
    engine_standins.dispatcher.reason = "no model answered"
    queue.enqueue(core, build_job(core, ["INT-001", "SR-001"]))
    assert worker.run_once(open_core(world), SESSION)
    root = Path(core.root)
    logged = {e.payload["id"]: e.payload for e in open_core(world).events() if e.kind == "verdict"}
    assert list(logged) == ["INT-001"] and logged["INT-001"]["by"] == "jev"
    waiting = [j for j in jobs.queued(root, SESSION)
               if [r["id"] for r in j.inputs["records"]] == ["SR-001"]]
    assert len(waiting) == 1
    notes = (root / ".plumb" / "session" / SESSION / "agent_notes.json").read_text("utf-8")
    assert "SR-001" in notes


def test_ex2_an_answer_out_of_schema_is_a_wait_with_the_same_line(world: Path) -> None:
    model = FakeDispatcher().failing("schema", "verdicts: required")
    _, done = partly(world, model)
    assert [e["id"] for e in done.left] == ["SR-001"]
    assert "is waiting" in done.line and "verdicts: required" in done.line


def test_ex2_with_no_verdict_at_all_the_job_waits_instead_of_failing(world: Path) -> None:
    from plumb.understand import verdict

    core = configure(world)
    model = FakeDispatcher().failing("schema", "verdicts: required")
    with pytest.raises(verdict.Waiting) as wait:
        cascade(core, model)
    assert "verdicts: required" in wait.value.line


def test_ex3_a_request_too_large_waits_with_the_size_in_the_line(world: Path) -> None:
    model = FakeDispatcher().failing("start", "the request is 900000 characters, too large")
    _, done = partly(world, model)
    assert [e["id"] for e in done.left] == ["SR-001"]
    assert "900000 characters, too large" in done.line
    again = cascade(open_core(world), model, ClearsIntent())
    assert again.line == ""                                  # said once


def test_ex4_every_record_answered_nothing_waits_and_no_line(world: Path) -> None:
    model = FakeDispatcher({"judge": verdict_answer(("SR-001", "supported", 0.9))})
    _, done = partly(world, model)
    assert done.left == () and done.line == ""
    assert sorted(v["id"] for v in done.answer["verdicts"]) == ["INT-001", "SR-001"]
