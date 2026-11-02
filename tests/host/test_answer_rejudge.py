"""The owner's answer is kept with its question and the judge runs again (task 3 of the
judge-approval plan). The PostToolUse hook logs a question-tool answer with its question and
options, matches it to the judge's open questions (``judge_questions.json``) and queues a bare
judge job; the premise then carries the answer at the record's version, and JEV receives the
question with the answer."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from understand.test_judge_job import (
    SESSION,
    intent_text,
    log_prompt,
    requirement_text,
)

from plumb.api import open_core
from plumb.contracts import Judgment
from plumb.hosts.claude_code import question_answer
from plumb.understand import cmd_clarify, files, jobs, judge, premise, verdict

MESSAGE = "Pages should load faster."
ASK = "Should every page load faster, or only the public ones?"


@pytest.fixture
def world(repo: Path, write_record) -> Path:
    digest = log_prompt(repo, MESSAGE)
    write_record(repo, intent_text(1, MESSAGE, "Make pages load faster", prompt=digest))
    write_record(repo, requirement_text(
        1, "Pages load in two seconds", "Public pages load within two seconds", intent=1,
        examples=(("a public page", "it is requested", "it loads within 2 seconds"),)))
    return repo


def judge_asks(repo: Path, *questions: tuple[str, list[str]]) -> None:
    """The worker's open questions file: ``(question, record ids)`` each, at today's hashes."""
    index = open_core(repo).index()
    files.write_json_atomic(judge.questions_path(repo, SESSION), [
        {"key": judge.question_key(text), "job": "judge-0000000000000000",
         "records": [{"id": i, "hash": index[i].hash} for i in ids], "question": text,
         "header": "Which pages",
         "options": [{"label": "Public pages (Recommended)", "description": "Only those."},
                     {"label": "Every page", "description": "All of them."}]}
        for text, ids in questions])


def answer(repo: Path, hook_input, question: str, picked: Any, *,
           options: list[dict[str, str]] | None = None, raw: bool = False,
           **tool_input: Any) -> None:
    """The question tool returns ``picked`` for ``question`` (``raw``: ``picked`` is the whole
    tool response)."""
    shown = options or [{"label": "Public pages (Recommended)", "description": "Only those."},
                        {"label": "Every page", "description": "All of them."}]
    asked = {"questions": [{"question": question, "header": "Pages", "options": shown,
                            "multiSelect": False}], **tool_input}
    response = picked if raw else {"answers": {question: picked}}
    payload = hook_input("PostToolUse", tool_name="AskUserQuestion", tool_input=asked,
                         tool_response=response, session_id=SESSION)
    assert question_answer.main(stdin=io.StringIO(payload), stdout=io.StringIO(),
                                root=repo) == 0


def logged(repo: Path) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in open_core(repo).events() if e.kind == "question-answer"]


def judge_jobs(repo: Path) -> list[Any]:
    return [j for j in jobs.queued(repo, SESSION) if j.kind == "judge"]


class RecordingJev:
    """A JEV backend that records the premise each claim is judged against."""

    name = "jev"
    version = "jev-1"

    def __init__(self) -> None:
        self.premises: list[str] = []

    def approval(self, premise: str, hypothesis: str, *, subject: str,
                 claim_kind: str) -> Judgment:
        self.premises.append(premise)
        return Judgment(action="faithfulness", subject=subject, verdict="benign",
                        confidence=0.9, tier="accept", backend="jev:jev-1", fingerprint="f",
                        reasons=(), probability=0.9, confidence_label="high")


# ---- SR-212 ---------------------------------------------------------------------------------


@pytest.mark.sr("SR-212")
def test_ex5_the_log_holds_the_question_both_options_and_the_answer(
        world: Path, hook_input) -> None:
    """SR-212 EX-5: 'Run the slow tests now or later?' answered 'later' with the question tool:
    the log holds the question, both options and 'later', in this session."""
    answer(world, hook_input, "Run the slow tests now or later?", "later",
           options=[{"label": "now", "description": "Slower turn."},
                    {"label": "later", "description": "Faster turn."}])
    (entry,) = logged(world)
    assert entry == {"session": SESSION, "question": "Run the slow tests now or later?",
                     "options": [{"label": "now", "description": "Slower turn."},
                                 {"label": "later", "description": "Faster turn."}],
                     "answer": "later", "via": "question-tool"}
    assert judge_jobs(world) == []              # no judge question asked: nothing to re-judge


@pytest.mark.sr("SR-212")
def test_ex6_an_answer_is_kept_with_its_question_and_the_record_stays_proposed(
        world: Path, hook_input) -> None:
    """SR-212 EX-6: 'yes, that is what I meant' to the judge's question about a requirement:
    kept with its question and the records asked at their version; the requirement stays
    proposed; a bare judge job is queued and its premise holds the answer."""
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, ASK, "yes, that is what I meant")
    core = open_core(world)
    (entry,) = logged(world)
    assert entry["question"] == ASK and entry["answer"] == "yes, that is what I meant"
    assert entry["asked"]["records"] == [{"id": "SR-001", "hash": core.index()["SR-001"].hash}]
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert not [e for e in core.events() if e.kind == "approval"]
    (job,) = judge_jobs(world)
    assert job.inputs["records"] == ["SR-001"]          # bare: the worker rebuilds the premise
    (rebuilt,) = judge.recompute(core, job)["records"]
    digest = next(e.digest for e in core.events() if e.kind == "question-answer")
    assert rebuilt["premise"]["answers"] == [{"digest": digest, "question": ASK,
                                              "options": entry["options"],
                                              "answer": "yes, that is what I meant"}]
    assert judge.open_questions(core, SESSION) == []


@pytest.mark.sr("SR-212")
@pytest.mark.parametrize("response", [{"answers": {}}, {}, "dismissed", None])
def test_ex7_a_dismissed_question_logs_nothing_and_queues_nothing(
        world: Path, hook_input, response: object) -> None:
    """SR-212 EX-7: the owner dismisses the question: nothing is logged as an answer."""
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, ASK, response, raw=True)
    assert logged(world) == [] and judge_jobs(world) == []


@pytest.mark.sr("SR-212")
def test_ex8_jevs_claim_holds_the_question_and_the_answer_not_a_alone(
        repo: Path, write_record, hook_input) -> None:
    """SR-212 EX-8: an intent quoting "A", the question offering A. Mostly in the background and
    B. A checkpoint every turn: the premise JEV receives holds the question and the answer."""
    digest = log_prompt(repo, "A")
    write_record(repo, intent_text(1, "A", "Checks run in the background", prompt=digest))
    question = "How should the checks run?"
    judge_asks(repo, (question, ["INT-001"]))
    answer(repo, hook_input, question, "A", options=[
        {"label": "A", "description": "Mostly in the background"},
        {"label": "B", "description": "A checkpoint every turn"}])
    core = open_core(repo)
    jev = RecordingJev()
    (entry,) = judge.entries_for(core, ["INT-001"])
    assert verdict.jev_verdict(core, entry, jev, None) is not None
    assert jev.premises == ["A\n\nQuestion: How should the checks run?\nOptions: A (Mostly in "
                            "the background); B (A checkpoint every turn)\nAnswer: A"]


@pytest.mark.sr("SR-212")
def test_ex10_a_full_sentence_is_passed_unchanged(world: Path) -> None:
    """SR-212 EX-10: a quote of a full sentence, no answer: JEV receives it as it is."""
    core = open_core(world)
    jev = RecordingJev()
    (entry,) = judge.entries_for(core, ["INT-001"])
    verdict.jev_verdict(core, entry, jev, None)
    assert jev.premises == [MESSAGE]


# ---- SR-209, SR-208 -------------------------------------------------------------------------


@pytest.mark.sr("SR-209")
def test_ex4_an_answer_follows_the_record_to_its_later_wording(
        world: Path, write_record, hook_input) -> None:
    """SR-209 EX-4: the requirement is reworded after its question was put to the owner: the
    answer names the version asked, and the reworded record, confirmed on no version yet, goes
    back to the judge with the answer in its premise."""
    judge_asks(world, (ASK, ["SR-001"]))
    asked_hash = open_core(world).index()["SR-001"].hash
    write_record(world, requirement_text(
        1, "Pages load in one second", "Public pages load within one second", intent=1,
        examples=(("a public page", "it is requested", "it loads within 1 second"),)))
    answer(world, hook_input, ASK, "Public pages (Recommended)")
    core = open_core(world)
    record = core.index()["SR-001"]
    assert record.hash != asked_hash
    assert logged(world)[0]["asked"]["records"] == [{"id": "SR-001", "hash": asked_hash}]
    assert [a["answer"] for a in premise.premise_of(core, record).answers] == [
        "Public pages (Recommended)"]
    (job,) = judge_jobs(world)
    (rebuilt,) = judge.recompute(core, job)["records"]
    assert rebuilt["hash"] == record.hash and rebuilt["premise"]["answers"]


@pytest.mark.sr("SR-208")
def test_ex5_the_answer_is_read_from_the_tools_record_not_the_agents_restatement(
        world: Path, hook_input) -> None:
    """SR-208 EX-5: the agent's own restatement ('now') rides in the tool input; the host's
    record of the call says 'later': 'later' is logged as the owner's answer."""
    question = "Run the slow tests now or later?"
    answer(world, hook_input, question, "later", answers={question: "now"},
           options=[{"label": "now", "description": ""}, {"label": "later", "description": ""}])
    assert [e["answer"] for e in logged(world)] == ["later"]


# ---- matching -------------------------------------------------------------------------------


@pytest.mark.sr("SR-212")
def test_a_question_with_other_spacing_and_case_matches_by_key(world: Path, hook_input) -> None:
    """Two open questions; the agent passes one with other case and spacing and a
    "(Recommended)" mark: it matches that question by its key, not the other."""
    other = "Should the admin pages load faster too?"
    judge_asks(world, (ASK, ["SR-001"]), (other, ["INT-001"]))
    answer(world, hook_input, "  SHOULD every page load faster,\n or only the public ones? "
                              "(Recommended)", "Every page")
    (entry,) = logged(world)
    assert entry["asked"]["key"] == judge.question_key(ASK)
    assert [r["id"] for r in entry["asked"]["records"]] == ["SR-001"]
    assert [q["question"] for q in judge.unanswered(open_core(world), SESSION)] == [other]


@pytest.mark.sr("SR-212")
def test_an_answer_given_in_another_session_closes_the_question(
        world: Path, hook_input) -> None:
    """report-c4cdbf4b: the owner answers the exact question through the question tool in
    another Claude session: the question is answered whichever session asked it."""
    judge_asks(world, (ASK, ["SR-001"]))
    shown = [{"label": "Every page", "description": ""}, {"label": "Public", "description": ""}]
    payload = hook_input(
        "PostToolUse", tool_name="AskUserQuestion", session_id="other-session",
        tool_input={"questions": [{"question": ASK, "header": "Pages", "multiSelect": False,
                                   "options": shown}]},
        tool_response={"answers": {ASK: "Every page"}})
    assert question_answer.main(stdin=io.StringIO(payload), stdout=io.StringIO(),
                                root=world) == 0
    assert judge.unanswered(open_core(world), SESSION) == []


@pytest.mark.sr("SR-212")
def test_a_cli_question_reworded_and_answered_in_a_live_session_is_settled(
        world: Path, hook_input) -> None:
    """report-c06d5563: the judge filed the question under "cli"; a live session asks it in
    its own words, before or after registering the wording: the owner's answer settles it."""
    judge_asks(world, (ASK, ["SR-001"]))
    cli = files.session_dir(world, "cli")
    cli.mkdir(parents=True, exist_ok=True)
    judge.questions_path(world, SESSION).rename(judge.questions_path(world, "cli"))
    worded = "Speed up every page or only the public ones?"
    options = [{"label": "Every page", "description": ""}, {"label": "Public", "description": ""}]
    answer(world, hook_input, worded, "Every page")      # asked before the wording is registered
    assert [q["question"] for q in judge.unanswered(open_core(world), "cli")] == [ASK]
    judge.reword(open_core(world), SESSION, [judge.question_key(ASK)], worded, "Pages", options)
    assert judge.unanswered(open_core(world), "cli") == []
    assert judge.unanswered_anywhere(open_core(world)) == []


@pytest.mark.sr("SR-212")
def test_a_cli_question_is_matched_by_a_live_sessions_answer(world: Path, hook_input) -> None:
    judge_asks(world, (ASK, ["SR-001"]))
    files.session_dir(world, "cli").mkdir(parents=True, exist_ok=True)
    judge.questions_path(world, SESSION).rename(judge.questions_path(world, "cli"))
    answer(world, hook_input, ASK, "Every page")
    assert [r["id"] for r in logged(world)[0]["asked"]["records"]] == ["SR-001"]
    assert judge.unanswered(open_core(world), "cli") == []


@pytest.mark.sr("SR-212")
def test_a_reworded_question_falls_back_to_the_one_open_question(
        world: Path, hook_input) -> None:
    """One open question; the agent reworded it: the answer still names its records."""
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, "Faster: every page, or the public ones only?", "Every page")
    assert [r["id"] for r in logged(world)[0]["asked"]["records"]] == ["SR-001"]
    assert len(judge_jobs(world)) == 1


@pytest.mark.sr("SR-212")
def test_an_unmatched_answer_gives_the_one_line(world: Path, hook_input) -> None:
    """Two open questions, the agent asked something else: the answer is logged without
    ``asked``, no judge job is queued, and ``clarify --wait`` says the one line."""
    judge_asks(world, (ASK, ["SR-001"]), ("Should the admin pages load faster too?",
                                          ["INT-001"]))
    answer(world, hook_input, "Which colour should the button be?", "Every page")
    assert "asked" not in logged(world)[0] and judge_jobs(world) == []
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=1)
    assert (outcome.state, outcome.lines) == ("ask", [cmd_clarify.UNMATCHED])
    assert len(outcome.questions) == 2


@pytest.mark.sr("SR-212")
def test_an_unrelated_answer_is_not_taken_for_the_one_open_question(
        world: Path, hook_input) -> None:
    """One open question; the agent asks something else with its own options (SR-212 EX-4):
    the answer is logged without ``asked``, no judge job, and ``clarify --wait`` says the line."""
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, "Run the slow tests now or later?", "Later",
           options=[{"label": "Now", "description": "Wait for them."},
                    {"label": "Later", "description": "Run them at the end."}])
    assert "asked" not in logged(world)[0] and judge_jobs(world) == []
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=1)
    assert (outcome.state, outcome.lines) == ("ask", [cmd_clarify.UNMATCHED])
    assert len(outcome.questions) == 1


@pytest.mark.sr("SR-212")
def test_an_empty_answers_keeps_the_premise_digest(world: Path) -> None:
    """A premise without answers has the digest it had before answers existed; one with an
    answer has another."""
    core = open_core(world)
    found = premise.premise_of(core, core.index()["SR-001"])
    given = found.as_input()
    assert "answers" not in given
    old = {"messages": given["messages"], "question": given["question"],
           "parent": given["parent"]}
    assert found.digest == premise.input_digest(old) == given["messages"][0]["digest"]
    answered = premise.Premise(messages=found.messages, answers=(
        {"question": ASK, "options": [], "answer": "Every page"},))
    assert answered.digest != found.digest
