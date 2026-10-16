"""Phase I: the places where the lanes met and each was right on its own (plan 12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.contracts import DispatchError
from understand.test_judge_job import intent_text, log_prompt, requirement_text

pytestmark = pytest.mark.sr("SR-214", "SR-252", "SR-252", "SR-272")

SESSION = "s1"


def test_calibration_from_logged_scores_leaves_the_generated_no_examples_out(
        repo: Path, write_record) -> None:
    """A generated 'no' shares its source record's id and hash, so a logged verdict would
    score it as the record it was made from; no verdict covers it (SR-106)."""
    from plumb.approvals import approval_items
    from plumb.capture import calibrate
    from understand.fakes import as_worker

    digest = log_prompt(repo, "Build a calculator that adds and multiplies whole numbers.")
    write_record(repo, intent_text(1, "Build a calculator", "A calculator", prompt=digest))
    for n in range(1, 4):
        write_record(repo, requirement_text(
            n, f"Operation {n}", f"The calculator does operation {n}", intent=1,
            examples=((f"input {n}", "it runs", f"output {n}"),)))
    core = open_core(repo)
    core.log_append("events", "prompt", {"digest": digest, "session": SESSION,
                                         "at": "2026-10-10T10:00:00Z"})
    for n in range(1, 4):
        record = core.index()[f"SR-00{n}"]
        core.log_append("events", "verdict", {
            "job": "judge-1", "id": record.id, "hash": record.hash, "verdict": "supported",
            "beyond": [], "contradicts": [], "score": 0.9, "by": "jev",
            "judge": "jev:test/jev-1", "model": "test/jev-1",
            "premise_digest": "sha256:2"})
    with as_worker(repo, SESSION):
        for n in range(1, 4):
            core.log_append("events", "approval", {
                "records": approval_items(core, [f"SR-00{n}"]), "by": "owner-words",
                "label": "yes", "prompt_digest": digest, "evidence": "adds and multiplies",
                "job": "read-1",
                "message": "Build a calculator that adds and multiplies whole numbers.",
                "confidence": 0.9})
    fresh = open_core(repo)
    assert any(i.source.startswith("gen") for i in calibrate.labelled_set(fresh))
    entry, results = calibrate.calibrate(fresh)
    assert entry.payload["source"] == "logged"
    assert results["example-restatement"].generated_negatives == 0


def test_the_worker_keeps_the_count_of_a_pass_between_its_jobs(repo: Path) -> None:
    """The line of the backlog pass reads 10/160 while the next job starts, not 0 (SR-107)."""
    import time

    from plumb.progress import Reporter
    from plumb.understand import files
    from plumb.understand.worker import _Pass

    Reporter(repo, SESSION, "judge").update("judging the backlog", 10, 160)
    worker = _Pass(open_core(repo), SESSION, "token")
    reporter = Reporter(repo, SESSION, "judge")
    assert worker._carried(reporter) == (10, 160)
    worker._clear(reporter)
    assert files.progress_path(repo, SESSION).exists()          # the pass is not over
    data = files.read_json(files.progress_path(repo, SESSION))
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    files.write_json_atomic(files.progress_path(repo, SESSION), data)
    assert worker._carried(reporter) == (0, 0)                  # an old count is not the pass
    worker._clear(reporter)
    assert not files.progress_path(repo, SESSION).exists()
    Reporter(repo, SESSION, "judge").update("judging 3 records")
    worker._clear(reporter)
    assert not files.progress_path(repo, SESSION).exists()      # a lone job leaves no line


class _Asked:
    """A model that records what it was sent and answers like a quiet clarifier."""

    name = "asked"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def available(self) -> None:
        return None

    def run(self, job: Any, *, system: str, user: str, schema: Any, on_step: Any) -> Any:
        self.sent.append({"system": system, "user": user, "schema": schema})
        return {"intent": "no", "gap": False, "gaps": []}


def test_the_evaluation_set_gives_a_real_model_the_prompt_and_schema_not_the_answer() -> None:
    from plumb.understand import evalrun

    cases = evalrun.load_cases("clarify")[:2]
    model = _Asked()
    evalrun.run_cases(model, cases, "clarify")
    assert len(model.sent) == 2
    for sent in model.sent:
        assert "check whether a person's request is clear" in sent["system"]
        assert "expect" not in json.loads(sent["user"]) and sent["schema"]["required"]


def test_the_evaluation_set_reads_each_kinds_answer_its_own_way() -> None:
    from plumb.understand import evalrun

    read = {"entries": [{"id": "INT-008", "answer": "accepted"},
                        {"id": "SR-088", "answer": "change"}]}
    expect = {"entries": [{"id": "INT-008", "answer": "accepted"},
                          {"id": "SR-088", "answer": "change"}]}
    assert evalrun._answers_match("read", read, expect)
    assert not evalrun._answers_match("read", {"entries": [read["entries"][0]]}, expect)
    extra = {"entries": [*read["entries"], {"id": "SR-001", "answer": "accepted"}]}
    assert not evalrun._answers_match("read", extra, expect)    # an unasked confirmation
    verdicts = {"verdicts": [{"id": "INT-004", "verdict": "supported", "confidence": 0.9}]}
    assert evalrun._answers_match("judge", verdicts, {"verdicts": [
        {"id": "INT-004", "verdict": "supported"}]})
    assert not evalrun._answers_match("judge", verdicts, {"verdicts": [
        {"id": "INT-004", "verdict": "beyond"}]})


def test_a_model_answer_that_fails_the_schema_fails_its_case() -> None:
    from plumb.understand import evalrun

    class Broken(_Asked):
        def run(self, job: Any, **_: Any) -> Any:
            raise DispatchError("run", "the model could not be reached")

    (row,) = evalrun.run_cases(Broken(), evalrun.load_cases("clarify")[:1], "clarify")
    assert row["passed"] is False and row["error"].startswith("run:")

    class NoGapFlag(_Asked):
        def run(self, job: Any, **_: Any) -> Any:
            return {"intent": "no", "gaps": []}                  # the gap flag is required

    (row,) = evalrun.run_cases(NoGapFlag(), evalrun.load_cases("clarify")[:1], "clarify")
    assert row["passed"] is False and row["error"].startswith("schema:")


def test_a_late_confirmation_is_told_once_at_the_next_turn(repo: Path, write_record) -> None:
    """A read that finished after its turn ended is told with the next turn's summary, once
    (spec 9.1: collected at the next turn)."""
    from types import SimpleNamespace

    from plumb.approvals import approval_items
    from plumb.understand import summary
    from understand.fakes import as_worker
    from understand.test_read_job import int_text

    write_record(repo, int_text(8, "Internal features"))
    core = open_core(repo)
    ctx = SimpleNamespace(session_id=SESSION, root=repo, deadline=None)
    first = summary.stop_parts(ctx, core, {"prompt_digest": "sha256:turn1",
                                           "turn_start": 1.0})
    assert first.confirmations == ()
    message = "INT-008 ok"
    core.log_append("events", "prompt", {"digest": "sha256:turn1", "session": SESSION,
                                         "at": "2999-01-01T00:00:00Z"})
    with as_worker(repo, SESSION):
        core.log_append("events", "approval", {
            "records": approval_items(core, ["INT-008"]), "by": "owner-words",
            "prompt_digest": "sha256:turn1", "evidence": message, "message": message,
            "job": "read-1", "confidence": 0.9})
    fresh = open_core(repo)
    second = summary.stop_parts(ctx, fresh, {"prompt_digest": "sha256:turn2",
                                             "turn_start": 2.0})
    assert [line.endswith(message) for line in second.confirmations] == [True]
    third = summary.stop_parts(ctx, fresh, {"prompt_digest": "sha256:turn3",
                                            "turn_start": 3.0})
    assert third.confirmations == ()


def test_the_claude_command_is_given_a_schema_without_our_label() -> None:
    """The real claude command refuses a schema that carries ``id`` ("use $id"): the label
    names the schema in plumb and is left off the command line (found against the real model)."""
    from plumb.understand.dispatch.claude_code import ClaudeCodeDispatcher, cli_schema
    from plumb.understand.kinds import KINDS

    for module in (KINDS[name] for name in ("read", "judge", "clarify")):
        schema = dict(module.schema)
        assert "id" in schema or not schema
        assert "id" not in cli_schema(schema)
        assert cli_schema(schema).get("type") == schema.get("type")
    job = __import__("plumb.understand.files", fromlist=["x"]).make_job(
        "clarify", SESSION, "clarify.v1", {})
    argv = ClaudeCodeDispatcher(model="haiku").command("claude", job, "system", {
        "id": "x.v1", "type": "object"})
    assert json.loads(argv[argv.index("--json-schema") + 1]) == {"type": "object"}
