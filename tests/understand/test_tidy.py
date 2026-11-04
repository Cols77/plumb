"""SR-162: a background job reads the open cards against the owner's confirmed records and
withdraws the ones a confirmed record answers or that repeat another; the model is stubbed."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from plumb import stale
from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion, DispatchError
from plumb.understand import cardstore, files, summary, tidy, worker
from understand.test_judge_job import SESSION, requirement_text

pytestmark = pytest.mark.sr("SR-217")

SAYS = "A conflict may be answered through the agent in chat"


@pytest.fixture
def world(repo: Path, write_record, engine_standins):
    write_record(repo, requirement_text(1, "Chat answers", SAYS))
    cardstore.save(repo, SESSION, [CardState(
        id="conflict:1", kind="conflict", topic="Answer a conflict in chat",
        issue="may a conflict be answered through the agent", resolutions=("yes", "no"),
        questions=(ClarifyQuestion(id="conflict:1#1", text="in chat?"),))])
    return engine_standins


def _run(repo: Path, confirmation: str = "confirmed") -> Any:
    core = open_core(repo)
    core.status = lambda ids: {i: types.SimpleNamespace(confirmation=confirmation,
                                                        superseded_by=None) for i in ids}
    tidy.enqueue(core, SESSION)
    worker.run_once(core, SESSION)
    return core


def _answer(world, **verdict: Any) -> None:
    world.dispatcher.script = {"tidy": {"verdicts": [{"card": "conflict:1", **verdict}]}}


def _status(repo: Path) -> str:
    return cardstore.own_cards(repo, SESSION)[0].status


def _withdrawn(repo: Path) -> list[str]:
    """The logged reasons of the withdrawals (SR-218: each one is logged)."""
    return [str(e.payload.get("reason")) for e in open_core(repo).events()
            if e.kind == "card-withdrawn"]


def test_ex1_a_confirmed_record_that_answers_the_card_withdraws_it_quoting_it(
        repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote="through the agent in chat")
    _run(repo)
    assert _status(repo) == "withdrawn"
    (reason,) = _withdrawn(repo)                      # logged, quoting the record's words
    assert "SR-001" in reason and "through the agent in chat" in reason


def test_ex2_a_record_that_is_only_proposed_leaves_the_card(repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote="through the agent in chat")
    _run(repo, "proposed")
    assert _status(repo) == "open" and _withdrawn(repo) == []


def test_words_the_record_does_not_hold_leave_the_card(repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote="never in chat")
    _run(repo)
    assert _status(repo) == "open"


def test_ex3_two_stale_cards_asking_the_same_lose_one(repo: Path, write_record,
                                                      engine_standins) -> None:
    write_record(repo, requirement_text(62, "Calc", "adds"))
    for link in ("SR-062#0", "SR-062#1"):
        stale.add_card(repo, SESSION, link=link, record="SR-062", path="src/calc.py",
                       topic=f"Calc {link}", issue="the code changed", options=["keep", "undo"])
    engine_standins.dispatcher.script = {"tidy": {"verdicts": [
        {"card": "stale:SR-062#1", "verdict": "withdraw_duplicate", "other": "stale:SR-062#0"},
        {"card": "stale:SR-062#0", "verdict": "withdraw_duplicate", "other": "stale:SR-062#1"}]}}
    _run(repo)
    assert [c.id for c in cardstore.stale_cards(repo, SESSION)] == ["stale:SR-062#0"]
    (reason,) = _withdrawn(repo)                      # the log names the other question
    assert "Calc SR-062#0" in reason


def test_ex4_a_judge_that_cannot_be_reached_withdraws_nothing_and_says_so(
        repo: Path, world) -> None:
    _answer(world, verdict="withdraw_answered", record="SR-001", quote=SAYS)
    world.dispatcher.script = {"tidy": DispatchError("run", "the model could not be reached")}
    core = _run(repo)
    assert _status(repo) == "open" and _withdrawn(repo) == []
    assert summary.owner_line(core, SESSION) == ""   # SR-373: no owner line about it


def test_unsure_keeps_the_card(repo: Path, world) -> None:
    _answer(world, verdict="keep")
    _run(repo)
    assert _status(repo) == "open"


# -- SR-218: waiting questions (report-ec092f5e: the job read only the retired cards) ----------

ASKED = "Should a merged fix keep its branch?"
ANSWERED = "Does a landing delete the branch of a finished worktree?"
SAID = "remove the worktree but not the branch, remove duplicates"


def _waiting(repo: Path) -> str:
    """A judge question on SR-001 in a session, and the owner's earlier answer logged."""
    from plumb.understand import judge

    index = open_core(repo).index()
    files.write_json_atomic(judge.questions_path(repo, "cli"), [
        {"key": judge.question_key(ASKED), "job": "judge-0000000000000000", "header": "Branch",
         "records": [{"id": "SR-001", "hash": index["SR-001"].hash}], "question": ASKED,
         "options": [{"label": "Keep", "description": ""}, {"label": "Delete", "description": ""}]}])
    (entry,) = open_core(repo).log_append_many("events", [("question-answer", {
        "session": SESSION, "question": ANSWERED, "answer": SAID, "via": "question-tool",
        "options": []})])
    return entry.digest


def _tidy(repo: Path) -> None:
    core = open_core(repo)
    tidy.enqueue(core, SESSION)
    worker.run_once(core, SESSION)


def _left(repo: Path) -> list[str]:
    from plumb.understand import judge

    return [str(q.get("question")) for q in judge.open_anywhere(open_core(repo))]


def _close(world, digest: str, quote: str) -> None:
    from plumb.understand import judge

    world.dispatcher.script = {"tidy": {"verdicts": [], "questions": [
        {"question": judge.question_key(ASKED), "answer": digest, "quote": quote}]}}


def test_a_waiting_question_the_owners_answer_settles_closes_quoting_it(
        repo: Path, world) -> None:
    digest = _waiting(repo)
    assert _left(repo) == [ASKED]
    _close(world, digest, "remove the worktree but not the branch")
    _tidy(repo)
    assert _left(repo) == []
    (bound,) = [e for e in open_core(repo).events() if e.kind == "answer-bound"]
    assert bound.payload["by"] == "tidy" and bound.payload["answer"] == digest
    assert bound.payload["quote"] == "remove the worktree but not the branch"


def test_a_quote_not_in_the_answer_closes_nothing(repo: Path, world) -> None:
    _close(world, _waiting(repo), "delete the branch")
    _tidy(repo)
    assert _left(repo) == [ASKED]


def test_the_owner_can_reopen_a_closed_question(repo: Path, world, capsys) -> None:
    from plumb.understand import cmd_question

    _close(world, _waiting(repo), "remove the worktree but not the branch")
    _tidy(repo)
    assert _left(repo) == []
    assert cmd_question.run("question", ["--root", str(repo), "--session", SESSION,
                                         "reopen", ASKED[:20]]) == 0
    assert _left(repo) == [ASKED]


def test_the_job_reads_waiting_questions_with_no_card_open(repo: Path, world) -> None:
    from plumb.understand import cardstore as store

    store.save(repo, SESSION, [])
    _waiting(repo)
    assert tidy.build(open_core(repo), SESSION) is not None
