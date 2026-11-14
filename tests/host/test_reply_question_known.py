"""Case report-9316d1a2: a reply that only quotes a question the owner already has, or already
answered, files no new question; a question the owner has never seen is still filed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import ASK, answer, judge_asks, world  # noqa: F401
from understand.test_judge_job import SESSION

from iaso.api import open_core
from iaso.contracts import Job
from iaso.understand import judge, question

pytestmark = pytest.mark.sr("SR-223")

OPTIONS = [{"label": "Public pages", "effect": "accepted", "consequence": "Only those."},
           {"label": "Every page", "effect": "change", "consequence": "All of them."}]


def read_from_reply(repo: Path, text: str) -> list[dict[str, Any]]:
    """The reply reader's answer holds one question about SR-001; what is then filed."""
    core = open_core(repo)
    job = Job(id="question-0000000000000001", kind="question", session=SESSION,
              schema=question.SCHEMA_ID, inputs={"reply": text})
    question.apply(core, job, {"questions": [
        {"question": text, "options": OPTIONS, "records": ["SR-001"]}]})
    return [q for q in judge._logged_questions(repo, SESSION)
            if str(q.get("job", "")).startswith("reply:")]


def test_quoting_a_waiting_question_with_a_note_files_nothing(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    assert read_from_reply(world, ASK + " (the other session added a note)") == []


def test_quoting_an_answered_question_files_nothing(world: Path, hook_input) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, ASK, "Every page")
    assert read_from_reply(world, ASK) == []


def test_a_question_the_owner_never_saw_is_still_filed(world: Path) -> None:  # noqa: F811
    judge_asks(world, (ASK, ["SR-001"]))
    (filed,) = read_from_reply(world, "Should the admin pages get a cache too?")
    assert filed["key"] == judge.question_key("Should the admin pages get a cache too?")
