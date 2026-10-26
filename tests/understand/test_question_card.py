"""SR-167: a question in the agent's reply whose answer would change a record is raised as a
choice card at the turn end, or when the owner answers it first, raised and answered in one
step; a question that changes no record raises none. The model is stubbed."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.understand import cardstore, summary, worker
from understand.test_answer_once import _reply
from understand.test_clarify_context import _agent, _owner, _transcript
from understand.test_judge_job import SESSION, requirement_text

pytestmark = pytest.mark.sr("SR-223")

ASK = "Reword SR-001 to follow INT-028, or keep it?"
OPTIONS = [{"label": "Reword it", "effect": "change", "consequence": "Rewrites it"},
           {"label": "Keep it", "effect": "accepted", "consequence": "Confirms it"}]
ASKED = {"question": ASK, "options": OPTIONS, "records": ["SR-001"]}


@pytest.fixture
def world(repo: Path, write_record: Any, engine_standins: Any) -> Any:
    write_record(repo, requirement_text(1, "Export users", "export the user list as CSV"))
    return engine_standins


def _turn_end(repo: Path, tmp_path: Path, reply: str, found: list[dict[str, Any]], world: Any
              ) -> Any:
    transcript = _transcript(tmp_path / "t.jsonl", [_owner("go on"), _agent(reply)])
    world.dispatcher.script = {"question": {"questions": found}, "tidy": {"verdicts": []}}
    summary._turn_upkeep(open_core(repo), SESSION, {"turn_start": time.time() - 60},
                         str(transcript))
    worker.run_once(open_core(repo), SESSION)
    return open_core(repo)







def test_ex4_an_answer_to_such_a_question_is_only_logged(repo: Path, world: Any) -> None:
    question = "Run the slow tests now or later?"
    core = _reply(repo, world, "later", [],
                  {"intent": "no", "answers": {"question": question, "evidence": "later"}})
    assert cardstore.own_cards(repo, SESSION) == []
    assert [e.payload["question"] for e in core.events() if e.kind == "question-answer"] == [question]
