"""SR-163: an owner's clear answer to a question just put to them is logged with the question
and raises no new read-back; no card file is written."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt
from understand.test_clarify_job import SESSION

from iaso.api import open_core
from iaso.understand import clarify, gate, judge, queue, read, worker

pytestmark = pytest.mark.sr("SR-212")

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


def test_ex2_an_answer_to_a_question_in_the_last_reply_is_logged_with_it(
        repo: Path, engine_standins: Any) -> None:
    question = "Merge now or after the review?"
    core = _reply(repo, engine_standins, "after the review", [],
                  {"intent": "yes", "answers": {"question": question,
                                                "evidence": "after the review"},
                   "readback": {"proposal": "Your request: after the review"}})
    assert judge.open_questions(core, SESSION) == []     # no further question for the reply
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


def test_the_prompt_and_schema_ask_for_the_answer() -> None:
    assert "answers" in clarify.schema["properties"]
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(encoding="utf-8")
    assert "`answers`" in prompt and "last_reply" in prompt

