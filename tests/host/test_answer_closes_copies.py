"""report-307d2564: one owner answer settles a question once and for all. It closes every copy
of the question it answers: the same record and principle in other words, in another session
or checkout, or filed after the answer; a question on another principle about the same record
stays (SR-362 EX-4). The owner's own words close the question they answer and its copies open
now (SR-212 EX-13); an answer that picked no option leaves a later round free to ask again
(SR-362 EX-7). A wording the landing session registered closes the questions it covers in any
checkout (EX-16), and a decision on a branch not landed yet closes the question in main (EX-17)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import answer, logged, world  # noqa: F401
from understand.fakes import as_worker
from understand.test_judge_job import SESSION, decision_text, log_prompt

from iaso.api import open_core
from iaso.boundary import premerge
from iaso.understand import files, judge

pytestmark = pytest.mark.sr("SR-212")

PICKED = "Every page"

ASK = "Should every page load faster, or only the public ones?"
COPY = "Which pages should get faster? (asked again at the landing)"
OTHER = "Should the faster pages also work offline?"
OPTIONS = [{"label": "Public pages (Recommended)", "description": "Only those."},
           {"label": "Every page", "description": "All of them."}]


def ask(repo: Path, session: str, text: str, principle: str) -> str:
    """``session``'s open questions file gets one more judge question about SR-001."""
    path = judge.questions_path(repo, session)
    old = files.read_json(path)
    key = judge.question_key(text)
    files.write_json_atomic(path, [*(old if isinstance(old, list) else []), {
        "key": key, "job": "judge-0000000000000000", "principle": principle,
        "records": [{"id": "SR-001", "hash": open_core(repo).index()["SR-001"].hash}],
        "question": text, "header": "Which pages", "options": OPTIONS}])
    return key


def waiting(repo: Path, session: str) -> list[str]:
    return [str(q["question"]) for q in judge.open_questions(open_core(repo), session)]


def test_a_label_answer_closes_the_reworded_copy_in_another_session_not_another_topic(
        world: Path, hook_input: Any) -> None:  # noqa: F811
    ask(world, SESSION, ASK, "pages")
    ask(world, "landing", COPY, "pages")
    ask(world, "landing", OTHER, "offline")
    assert waiting(world, "landing") == [COPY, OTHER]
    answer(world, hook_input, ASK, "Every page")
    assert waiting(world, SESSION) == []
    assert waiting(world, "landing") == [OTHER]
    assert [row["question"] for row in premerge.open_questions_on(
        open_core(world), ["SR-001"])] == [OTHER]
    # a copy another session files after the answer is closed by it too
    ask(world, "later", "Only the public pages, or all of them?", "pages")
    assert waiting(world, "later") == []
    assert [str(q["question"]) for q in judge.unanswered_anywhere(open_core(world))] == [OTHER]


def test_free_text_closes_its_copies_open_now_not_a_later_round(
        world: Path, hook_input: Any) -> None:  # noqa: F811
    key = ask(world, SESSION, ASK, "pages")
    copy = ask(world, "landing", COPY, "pages")
    answer(world, hook_input, ASK, "the ones visitors see, not the admin ones")
    (said,) = logged(world)
    assert said["free_text"] is True and said["asked"]["keys"] == [key, copy]
    assert waiting(world, SESSION) == [] and waiting(world, "landing") == []
    # SR-362 EX-7: it picked no option, so a later round may ask the point again
    ask(world, "later", "Only the public pages, or all of them?", "pages")
    assert waiting(world, "later") == ["Only the public pages, or all of them?"]
    # the owner takes that closing back (iaso question reopen): it waits again
    open_core(world).log_append_many("events", [("answer-unbound", {
        "session": SESSION, "key": key})])
    assert waiting(world, SESSION) == [ASK]


def test_a_typed_reply_closes_the_topic_only_when_it_picked_an_option(world: Path) -> None:
    ask(world, SESSION, ASK, "pages")
    core = open_core(world)
    asked = {"job": "judge-0000000000000000", "key": judge.question_key(ASK), "principle": "pages",
             "records": [{"id": "SR-001", "hash": core.index()["SR-001"].hash}]}
    with as_worker(world, SESSION):
        core.log_append_many("events", [("pre-intent", {
            "session": SESSION, "via": "read", "text": "I don't know", "option": None,
            "question": ASK, "asked": asked})])
    ask(world, "later", COPY, "pages")
    assert waiting(world, SESSION) == [] and waiting(world, "later") == [COPY]
    with as_worker(world, SESSION):
        open_core(world).log_append_many("events", [("pre-intent", {
            "session": SESSION, "via": "read", "text": "every page", "option": PICKED,
            "question": ASK, "asked": asked})])
    assert waiting(world, "later") == []


def test_tidy_settling_a_question_closes_its_copy_in_another_session(world: Path) -> None:
    from iaso.understand import tidy

    key = ask(world, SESSION, ASK, "pages")
    ask(world, "landing", COPY, "pages")
    core = open_core(world)
    core.log_append_many("events", [("question-answer", {
        "session": SESSION, "question": "What about speed?", "answer": "Every page, please",
        "via": "question-tool", "options": []})])
    digest = next(e.digest for e in open_core(world).events() if e.kind == "question-answer")
    tidy._close_questions(open_core(world), SESSION, [
        {"question": key, "quote": "Every page", "answer": digest}], {})
    assert waiting(world, SESSION) == [] and waiting(world, "landing") == []


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_a_decision_on_a_branch_not_landed_closes_the_question_in_main(
        world: Path, write_record: Any, tmp_path: Path) -> None:  # noqa: F811
    _git(world, "add", "-A")
    _git(world, "commit", "-q", "--no-verify", "-m", "records")
    branch = tmp_path / "branch"
    _git(world, "worktree", "add", "-q", "-b", "feat", str(branch))
    log_prompt(world, "Every page")       # the owner's own words, said to the landing session
    ask(world, SESSION, ASK, "pages")
    assert waiting(world, SESSION) == [ASK]
    write_record(branch, decision_text(
        1, "Which pages should load faster (SR-001)?", "Every page", intent=1))
    assert waiting(world, SESSION) == []
    assert premerge.open_questions_on(open_core(world), ["SR-001"]) == []


def test_ex16_an_answer_to_a_registered_wording_closes_the_question_in_another_checkout(
        world: Path, hook_input: Any, tmp_path: Path) -> None:  # noqa: F811
    _git(world, "add", "-A")
    _git(world, "commit", "-q", "--no-verify", "-m", "records")
    branch = tmp_path / "branch"
    _git(world, "worktree", "add", "-q", "-b", "feat", str(branch))
    key = ask(branch, "ended", ASK, "pages")     # filed by a session of the other checkout
    assert waiting(branch, "ended") == [ASK]
    worded = "At the landing: which pages should get faster?"
    judge.reword(open_core(world), SESSION, [key], worded, "Pages", OPTIONS)
    answer(world, hook_input, worded, PICKED)
    (said,) = logged(world)
    assert said["asked"]["keys"] == [key]
    assert waiting(branch, "ended") == []
