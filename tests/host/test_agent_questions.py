"""SR-362: the agent puts the judge's questions in the owner's terms (``plumb question reword``,
merging those on one principle) and sends an obvious one back to the judge (``plumb question
pushback``), which withdraws it quoting what answers it, or keeps it. The model is scripted."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from host.test_answer_rejudge import (  # noqa: F401
    ASK,
    answer,
    judge_asks,
    judge_jobs,
    logged,
    world,
)
from understand.fakes import engine_standins  # noqa: F401 - the fixture
from understand.test_judge_job import SESSION

from plumb.api import open_core
from plumb.contracts import DispatchError
from plumb.understand import cmd_clarify, cmd_question, judge, worker

pytestmark = pytest.mark.sr("SR-362")

OTHER = "Should the faster pages also work offline?"
WORDED = "Should only the public pages get faster?"
SAID = "only the public pages, the others can wait"
SHOWN = [{"label": "Only public pages", "description": "The rest stays as it is."},
         {"label": "Every page", "description": "All pages get faster."}]


def question(repo: Path, *argv: str) -> int:
    return cmd_question.run("question", ["--root", str(repo), "--session", SESSION, *argv])


def reword(repo: Path, *covers: str, text: str = WORDED) -> int:
    return question(repo, "reword", *(a for c in covers for a in ("--covers", c)),
                    "--question", text, "--header", "Pages", "--options", json.dumps(SHOWN))


def events(repo: Path, kind: str) -> list[dict[str, Any]]:
    return [dict(e.payload) for e in open_core(repo).events() if e.kind == kind]


def open_keys(repo: Path) -> list[str]:
    return [str(q["key"]) for q in judge.open_questions(open_core(repo), SESSION)]


# ---- reword ----------------------------------------------------------------------------------


def test_ex1_an_answer_to_the_agents_wording_answers_the_question_it_covers(
        world: Path, hook_input) -> None:  # noqa: F811
    """EX-1: the judge's question asked in the agent's words, no id in them: the owner's answer
    answers the judge's question (``asked`` names it) and the judge reads it again."""
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK) == 0
    answer(world, hook_input, WORDED, "Only public pages", options=SHOWN)
    (entry,) = logged(world)
    assert entry["question"] == WORDED and "SR-" not in entry["question"]
    assert entry["asked"]["keys"] == [judge.question_key(ASK)]
    assert [r["id"] for r in entry["asked"]["records"]] == ["SR-001"]
    assert open_keys(world) == []
    (job,) = judge_jobs(world)
    assert job.inputs["records"] == ["SR-001"]


def test_one_wording_merges_two_questions_and_one_answer_settles_both(
        world: Path, hook_input) -> None:  # noqa: F811
    """Two judge questions hinging on one principle, merged in one wording (named by the start
    of each, comma-separated): one answer answers both, ``asked.keys`` naming each."""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    assert reword(world, "should every page,should the faster pages") == 0
    answer(world, hook_input, WORDED, "Every page", options=SHOWN)
    (entry,) = logged(world)
    assert entry["asked"]["keys"] == [judge.question_key(ASK), judge.question_key(OTHER)]
    assert {r["id"] for r in entry["asked"]["records"]} == {"SR-001", "INT-001"}
    assert open_keys(world) == []
    (job,) = judge_jobs(world)
    assert set(job.inputs["records"]) == {"SR-001", "INT-001"}


def test_a_wording_with_a_record_id_or_naming_no_open_question_is_refused(
        world: Path) -> None:  # noqa: F811
    """EX-1: the owner never sees an id; a key naming no open question records nothing."""
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK, text="Should SR-001 cover only public pages?") == 2
    assert reword(world, "a question nobody asked") == 1
    assert judge.reworded(world, SESSION) == []


def test_the_missed_check_counts_a_registered_wording_as_matched(
        world: Path, hook_input) -> None:  # noqa: F811
    """SR-212's check: the last answer, to a wording the agent registered, is no question of
    its own, even when the question it covered left meanwhile (the judge dropped it)."""
    judge_asks(world, (ASK, ["SR-001"]), (OTHER, ["INT-001"]))
    assert reword(world, OTHER, text="Should they work offline?") == 0
    judge_asks(world, (ASK, ["SR-001"]))
    answer(world, hook_input, "Should they work offline?", "Only public pages", options=SHOWN)
    outcome = cmd_clarify.wait(open_core(world), SESSION, timeout=10)
    assert outcome.state == "ask"
    assert outcome.lines == [cmd_clarify.ASK_QUESTIONS.format(n=1)]


# ---- pushback --------------------------------------------------------------------------------


def _owner_said_earlier(repo: Path, hook_input) -> None:
    answer(repo, hook_input, "Which pages matter most?", SAID,
           options=[{"label": SAID, "description": ""}, {"label": "all", "description": ""}])


def _push_back(repo: Path, engine_standins: Any, ruling: Any,
               reason: str = f'You said: "{SAID}"') -> Any:
    engine_standins.dispatcher.script = {"pushback": ruling}
    assert question(repo, "pushback", "should every page", "--reason", reason) == 0
    return cmd_clarify.wait(open_core(repo), SESSION, timeout=10)   # runs the judge's reading


def test_ex2_a_question_the_owner_already_answered_is_withdrawn_quoting_the_answer(
        world: Path, hook_input, engine_standins: Any) -> None:  # noqa: F811
    """EX-2: sent back quoting the owner's earlier answer: the judge withdraws it, quoting it,
    and the owner is not asked."""
    _owner_said_earlier(world, hook_input)
    judge_asks(world, (ASK, ["SR-001"]))
    outcome = _push_back(world, engine_standins, {"verdict": "withdraw",
                                                  "quote": "only the public pages"})
    assert outcome.state == "ready"
    assert open_keys(world) == []
    (ruling,) = events(world, "question-ruling")
    assert ruling["ruling"] == "withdrawn" and ruling["quote"] == "only the public pages"
    assert ruling["by"] == "owner" and ruling["reason"] == f'You said: "{SAID}"'


def test_ex3_a_question_the_judge_keeps_is_asked_unchanged(
        world: Path, hook_input, engine_standins: Any) -> None:  # noqa: F811
    """EX-3: the judge disagrees: the question is kept and asked, its words unchanged."""
    _owner_said_earlier(world, hook_input)
    judge_asks(world, (ASK, ["SR-001"]))
    outcome = _push_back(world, engine_standins, {"verdict": "keep"}, reason="obvious")
    assert outcome.state == "ask"
    assert [q["question"] for q in outcome.questions] == [ASK]
    (ruling,) = events(world, "question-ruling")
    assert ruling["ruling"] == "kept" and ruling["reason"] == "obvious"


def test_a_withdrawal_quoting_words_the_owner_never_said_keeps_the_question(
        world: Path, hook_input, engine_standins: Any) -> None:  # noqa: F811
    """EX-3: only the owner's words or an approved record answer it; the agent's reason does
    not."""
    _owner_said_earlier(world, hook_input)
    judge_asks(world, (ASK, ["SR-001"]))
    _push_back(world, engine_standins, {"verdict": "withdraw", "quote": "every page matters"},
               reason="every page matters")
    assert open_keys(world) == [judge.question_key(ASK)]
    assert events(world, "question-ruling")[0]["ruling"] == "kept"


@pytest.mark.parametrize("ruling", [{"verdict": "keep"},
                                    DispatchError("run", "the model could not be reached")])
def test_ex4_the_agent_cannot_drop_a_question_and_the_log_shows_push_back_and_ruling(
        world: Path, engine_standins: Any, ruling: Any) -> None:  # noqa: F811
    """EX-4: an irrelevant question: rewording drops nothing, and a push-back the judge keeps,
    or cannot read, leaves it open; the log shows the push-back and any ruling."""
    judge_asks(world, (ASK, ["SR-001"]))
    assert reword(world, ASK) == 0
    assert open_keys(world) == [judge.question_key(ASK)]
    _push_back(world, engine_standins, ruling, reason="irrelevant to this change")
    worker.run_once(open_core(world), SESSION)
    assert open_keys(world) == [judge.question_key(ASK)]
    (pushed,) = events(world, "question-pushback")
    assert pushed["reason"] == "irrelevant to this change"
    assert pushed["key"] == judge.question_key(ASK)
    rulings = events(world, "question-ruling")
    assert [r["ruling"] for r in rulings] == ([] if isinstance(ruling, Exception) else ["kept"])
