"""SR-163: an owner's clear answer to a question just put to them is applied to that card (or
logged with the question) and raises no new read-back card; an unclear one leaves it open."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.test_clarify_job import SESSION, _asked, _by_kind, _cards, _gap
from understand.test_read_cards import pinned, trial_card
from understand.test_read_job import make_core, open_card, record_text, state

from plumb.api import open_core
from plumb.understand import clarify, gate, queue, read, worker

pytestmark = pytest.mark.sr("SR-212")

FORMAT = {"intent": "yes", "topic": "export", "gaps": [_gap("format", "Which format?",
                                                            blocking=True)]}
NO_CARD = {"gap": False, "gaps": []}


def _reply(repo: Path, engine_standins: Any, text: str, reads: list[dict],
           clarified: dict[str, Any]) -> Any:
    """The owner replies ``text``: the reader's entries and the request check's answer are
    scripted, both jobs run as live (the check needs the read)."""
    core = open_core(repo)
    digest = log_prompt(repo, text, session=SESSION)
    gate.close(repo, SESSION, digest, "your request is being checked")
    engine_standins.dispatcher.script = {"read": {"entries": reads},
                                         "clarify": {**NO_CARD, **clarified}}
    after = read.build(core, SESSION, message={"digest": digest, "text": text})
    if after is not None:
        queue.enqueue(core, after)
    job = clarify.build(core, SESSION, message={"digest": digest, "text": text},
                        after=after.id if after else None)
    assert job is not None
    worker.run_once(core, SESSION, job.id)
    return open_core(repo)


def _status(repo: Path) -> dict[str, str]:
    return {c.id: c.status for c in _cards(repo)}


@pytest.mark.parametrize("intent", ["no", "yes"])
def test_ex1_an_option_number_answers_the_card_shown_in_text(
        repo: Path, engine_standins: Any, intent: str) -> None:
    _asked("let users export their data", FORMAT, repo, engine_standins)
    (card,) = _by_kind(repo, "choice")
    readback = _by_kind(repo, "clarify")[0].id
    core = _reply(repo, engine_standins, "2",
                  [{"id": f"{card.id}/format", "hash": "", "answer": "change",
                    "change": "the second way", "evidence": "2", "confidence": 0.95}],
                  {"intent": intent, "answers": {"card": card.id, "evidence": "2"},
                   "readback": {"proposal": "Your request: 2"}, "replaces": [card.id]})
    by_id = {c.id: c for c in _cards(repo)}
    assert by_id[card.id].status == "answered"
    assert by_id[card.id].answers[0].answer == "change: the second way"
    assert set(by_id) == {card.id, readback}              # no 'Your request: 2' card
    assert not gate.is_closed(repo, SESSION)
    assert any(e.payload.get("evidence") == "2" for e in core.events() if e.kind == "read-entry")


def test_ex2_an_answer_to_a_question_in_the_last_reply_is_logged_with_it(
        repo: Path, engine_standins: Any) -> None:
    question = "Merge now or after the review?"
    core = _reply(repo, engine_standins, "after the review", [],
                  {"intent": "yes", "answers": {"question": question,
                                                "evidence": "after the review"},
                   "readback": {"proposal": "Your request: after the review"}})
    assert _cards(repo) == []
    (logged,) = [e for e in core.events() if e.kind == "question-answer"]
    assert logged.payload["question"] == question
    assert logged.payload["answer"] == "after the review"
    assert logged.payload["session"] == SESSION
    assert not gate.is_closed(repo, SESSION)


def test_ex2_words_that_are_not_in_the_message_record_nothing(
        repo: Path, engine_standins: Any) -> None:
    core = _reply(repo, engine_standins, "after the review", [],
                  {"intent": "no", "answers": {"question": "Merge now?", "evidence": "now"}})
    assert [e for e in core.events() if e.kind == "question-answer"] == []


def test_ex3_a_partial_answer_leaves_the_card_open_and_records_nothing(
        repo: Path, engine_standins: Any) -> None:
    _asked("let users export their data", FORMAT, repo, engine_standins)
    (card,) = _by_kind(repo, "choice")
    before = _status(repo)
    text = "maybe 2, but I am not sure about the skills"
    core = _reply(repo, engine_standins, text,
                  [{"id": f"{card.id}/format", "hash": "", "answer": "open",
                    "evidence": text, "confidence": 0.4}],
                  {"intent": "yes", "replaces": [card.id],
                   "readback": {"proposal": "Your request: maybe 2"}})
    assert _status(repo) == before
    assert [e for e in core.events() if e.kind in ("question-answer", "approval")] == []
    assert gate.is_closed(repo, SESSION)                    # the card still holds the gate


def test_ex4_a_yes_to_a_card_about_one_record_confirms_only_that_record(
        repo: Path, write_record: Any, engine_standins: Any) -> None:
    core = make_core(repo, write_record, [record_text(n) for n in (2, 3)])
    open_card(core, pinned(core, trial_card("t1", ["SR-002"])))
    core = open_core(repo)
    state(core, ["SR-003"])
    core = _reply(repo, engine_standins, "yes",
                  [{"id": "t1/q0", "hash": "", "answer": "accepted", "evidence": "yes",
                    "confidence": 0.95}],
                  {"intent": "no", "answers": {"card": "t1", "evidence": "yes"}})
    approved = {r["id"] for e in core.events() if e.kind == "approval"
                for r in e.payload["records"]}
    assert approved == {"SR-002"}
    assert _status(repo)["t1"] == "answered"
    assert not [c for c in _cards(repo) if c.id.startswith("clarify:")]


def test_the_prompt_and_schema_ask_for_the_answer() -> None:
    assert "answers" in clarify.schema["properties"]
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(encoding="utf-8")
    assert "`answers`" in prompt and "last_reply" in prompt

