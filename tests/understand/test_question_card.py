"""SR-167: a question in the agent's reply whose answer would change a record is raised as a
choice card at the turn end, or when the owner answers it first, raised and answered in one
step; a question that changes no record raises none. The model is stubbed."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from understand.test_answer_once import _reply
from understand.test_clarify_context import _agent, _owner, _transcript
from understand.test_judge_job import SESSION, requirement_text

from plumb.api import open_core
from plumb.hosts.claude_code.hookio import Deadline, HookContext
from plumb.understand import cardstore, summary, worker

pytestmark = pytest.mark.sr("SR-167")

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
    ctx = HookContext("stop", {"transcript_path": str(transcript)}, repo, SESSION, Deadline(3000))
    summary.stop_parts(ctx, open_core(repo), {"turn_start": time.time() - 60})
    worker.run_once(open_core(repo), SESSION)
    return open_core(repo)


def test_ex1_a_record_changing_question_in_the_reply_raises_a_choice_card(
        repo: Path, tmp_path: Path, world: Any) -> None:
    core = _turn_end(repo, tmp_path, ASK, [ASKED], world)
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "choice"]
    assert card.status == "open" and card.issue == ASK
    assert card.resolutions == ("Reword it", "Keep it")
    assert card.questions[0].record == "SR-001"
    assert "SR-001" in card.evidence
    assert "Export users" in (summary.waiting_line(repo, SESSION, core) or "")  # the agent is told


def test_ex2_the_owner_answering_that_card_answers_it_and_raises_no_read_back(
        repo: Path, tmp_path: Path, world: Any) -> None:
    _turn_end(repo, tmp_path, ASK, [ASKED], world)
    (card,) = cardstore.own_cards(repo, SESSION)
    _reply(repo, world, "reword it",
           [{"id": f"{card.id}/{card.questions[0].id}", "hash": "", "answer": "change",
             "change": "Reword it", "evidence": "reword it", "confidence": 0.95}],
           {"intent": "no", "answers": {"card": card.id, "evidence": "reword it"}})
    cards = cardstore.own_cards(repo, SESSION)
    assert [(c.id, c.status) for c in cards] == [(card.id, "answered")]


def test_ex2_a_clarify_that_reads_the_answer_as_a_request_still_raises_no_read_back(
        repo: Path, tmp_path: Path, world: Any) -> None:
    _turn_end(repo, tmp_path, ASK, [ASKED], world)
    (card,) = cardstore.own_cards(repo, SESSION)
    _reply(repo, world, "reword it please",
           [{"id": f"{card.id}/{card.questions[0].id}", "hash": "", "answer": "change",
             "change": "Reword it", "evidence": "reword it please", "confidence": 0.95}],
           {"intent": "yes", "topic": "q", "gap": False, "gaps": []})
    cards = cardstore.own_cards(repo, SESSION)
    assert [(c.id, c.status) for c in cards] == [(card.id, "answered")]


def test_ex3_an_answer_before_any_card_raises_the_card_and_applies_it(
        repo: Path, world: Any) -> None:
    core = _reply(repo, world, "keep it", [],
                  {"intent": "no", "answers": {**ASKED, "picked": "Keep it",
                                               "evidence": "keep it"}})
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "choice"]
    assert card.status == "answered" and card.answers[0].answer == "accepted"
    approved = [e for e in core.events() if e.kind == "approval"]
    assert [r["id"] for e in approved for r in e.payload["records"]] == ["SR-001"]
    assert approved[0].payload["evidence"] == "keep it"
    (logged,) = [e for e in core.events() if e.kind == "question-answer"]
    assert logged.payload["question"] == ASK


def test_ex4_a_question_that_changes_no_record_raises_no_card(
        repo: Path, tmp_path: Path, world: Any) -> None:
    _turn_end(repo, tmp_path, "Run the slow tests now or later?", [], world)
    assert cardstore.own_cards(repo, SESSION) == []


def test_ex4_an_answer_to_such_a_question_is_only_logged(repo: Path, world: Any) -> None:
    question = "Run the slow tests now or later?"
    core = _reply(repo, world, "later", [],
                  {"intent": "no", "answers": {"question": question, "evidence": "later"}})
    assert cardstore.own_cards(repo, SESSION) == []
    assert [e.payload["question"] for e in core.events() if e.kind == "question-answer"] == [question]
