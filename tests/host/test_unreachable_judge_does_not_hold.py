"""SR-378 EX-4: with no judge reachable an ordinary message holds nothing: the edit gate stays
open, ``clarify --wait`` answers ``ready`` (a judge job that failed included), and the prompt
hook says once that the judge is unreachable."""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeVerify
from host.test_intent_change_gate import SESSION, records  # noqa: F401

from plumb.api import open_core
from plumb.contracts import JobError, JobResult
from plumb.hosts.claude_code import pretool, prompt
from plumb.judgment import JudgmentUnavailable
from plumb.understand import cmd_clarify, files, gate, judge, queue

pytestmark = pytest.mark.sr("SR-378")

UNREACHABLE = "judging unavailable"


class NoJudge:
    name = "none"

    def intent_change(self, prompt: str, confirmed: Sequence[Any]) -> Sequence[Any]:
        raise JudgmentUnavailable("JEV", "timed out")


def _say(repo: Path, hook_input, text: str) -> str:
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", prompt=text, session_id=SESSION)
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=FakeVerify(),
                       backend=NoJudge()) == 0
    return out.getvalue()


def test_ex4_no_judge_holds_nothing_and_is_said_once(
        records: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    said = [_say(records, hook_input, text).count(UNREACHABLE)
            for text in ("make add subtract instead, SR-001", "and make add faster, SR-001")]
    assert said == [1, 0]
    assert gate.state(records, SESSION).state == "open"
    assert pretool.decide(records, SESSION, "Edit", {"file_path": "src/add.py"}) == {}
    core = open_core(records)
    job = judge.build(core, SESSION, records=["SR-001"])
    assert job is not None
    queue.enqueue(core, job)
    files.write_json_atomic(files.results_dir(records, SESSION) / f"{job.id}.json",
                            files.result_to_json(JobResult(
                                job=job.id, status="error", answer=None,
                                error=JobError(step="run", message="no model answered"))))
    (files.ran_dir(records, SESSION) / job.id).parent.mkdir(parents=True, exist_ok=True)
    (files.ran_dir(records, SESSION) / job.id).write_text("", encoding="utf-8")
    outcome = cmd_clarify.wait(open_core(records), SESSION, timeout=5)
    assert outcome.state == "ready" and gate.state(records, SESSION).state == "open"
