"""SR-216: a question that no longer stands is withdrawn by plumb right after the link it holds
is settled (the withdrawal is logged), and a judge question whose records are superseded or all approved is no longer
asked; never told in an owner line (SR-373)."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest
from core.test_stale_resolve import (  # noqa: F401
    LINK,
    REFORMATTED,
    Runner,
    _backend,
    _edit,
    project,
)

from plumb import links, stale
from plumb.api import open_core
from plumb.understand import judge
from understand.test_judge_job import SESSION, requirement_text

pytestmark = pytest.mark.sr("SR-216")


def _question_for_link(root: Path) -> None:
    stale.ask_owner(open_core(root), SESSION, link=LINK, record="SR-001",
                    topic="Adds numbers", issue="the code changed", options=["keep", "undo"])


def _stale_questions(root: Path) -> list[str]:
    return [str(q["job"]) for q in judge.open_questions(open_core(root), SESSION)]


def test_ex1_repin_withdraws_the_stale_question(project: Path) -> None:
    _edit(project, REFORMATTED)
    _question_for_link(project)
    assert _stale_questions(project) == [f"stale:{LINK}"]
    links.repin_after_tests(open_core(project), LINK, runner=Runner(), judge=_backend("cosmetic"))
    assert _stale_questions(project) == []
    (entry,) = [e for e in open_core(project).events() if e.kind == "question-withdrawn"]
    assert entry.payload["reason"] == "link" and entry.payload["link"] == LINK    # logged


def test_unlink_withdraws_the_question_of_a_link_that_is_gone(project: Path) -> None:
    _edit(project, REFORMATTED)
    _question_for_link(project)
    links.unlink(open_core(project), LINK, "the code moved")
    assert _stale_questions(project) == []
    assert [e.payload["reason"] for e in open_core(project).events()
            if e.kind == "question-withdrawn"] == ["link"]


def test_ex4_a_still_stale_question_stays(project: Path) -> None:  # noqa: F811
    _edit(project, REFORMATTED)
    _question_for_link(project)
    assert _stale_questions(project) == [f"stale:{LINK}"]


# ---- judge questions: no longer asked once their records stand settled (EX-2, EX-3, EX-8)


def _ask(repo: Path, *ids: str) -> Any:
    core = open_core(repo)
    judge.add_question(core, SESSION, {
        "key": judge.question_key("Should pages load fast?"), "job": "judge-x",
        "records": [{"id": i, "hash": core.index()[i].hash} for i in ids],
        "principle": "", "blocking": False, "diagram": False,
        "question": "Should pages load fast?", "header": "Speed",
        "options": [{"label": "Yes (Recommended)", "description": "Faster."},
                    {"label": "No", "description": "Simpler."}]})
    return core


def _with_status(core: Any, confirmed: set[str]) -> Any:
    real = core.status

    def status(ids: Any = None) -> Any:
        return {i: types.SimpleNamespace(**{**vars(s), "confirmation": "confirmed"})
                if i in confirmed else s for i, s in real(ids).items()}
    core.status = status
    return core


def test_ex2_a_question_on_a_superseded_requirement_is_no_longer_asked(
        repo: Path, write_record) -> None:
    write_record(repo, requirement_text(1, "Pages", "Pages load in a second"))
    _ask(repo, "SR-001")
    assert judge.open_questions(open_core(repo), SESSION)
    write_record(repo, requirement_text(2, "Pages", "Pages load in half a second",
                                        links=[{"kind": "supersedes", "to": "SR-001"}]))
    assert judge.open_questions(open_core(repo), SESSION) == []


def test_ex3_ex8_approved_records_settle_the_question_only_when_all_are(
        repo: Path, write_record) -> None:
    for n in (1, 2, 3):
        write_record(repo, requirement_text(n, f"Pages {n}", f"Pages load fast, part {n}"))
    _ask(repo, "SR-001", "SR-002", "SR-003")
    two = _with_status(open_core(repo), {"SR-001", "SR-002"})
    assert [q["key"] for q in judge.open_questions(two, SESSION)]          # EX-8: one left
    every = _with_status(open_core(repo), {"SR-001", "SR-002", "SR-003"})
    assert judge.open_questions(every, SESSION) == []                      # EX-3


def test_ex6_a_question_whose_branch_is_gone_is_not_listed(
        repo: Path, write_record) -> None:
    write_record(repo, requirement_text(1, "Pages", "Pages load in a second"))
    core = _ask(repo, "SR-001")
    path = judge.questions_path(repo, SESSION)
    asked = judge.files.read_json(path)
    judge.files.write_json_atomic(path, [{**q, "branch": "deleted-branch"} for q in asked])
    assert judge.open_questions(core, SESSION) == []


def test_ex7_a_withdrawn_question_leaves_its_records_not_yet_approved(
        repo: Path, write_record) -> None:
    write_record(repo, requirement_text(1, "Pages", "Pages load in a second"))
    _ask(repo, "SR-001")
    write_record(repo, requirement_text(2, "Pages", "Pages load in half a second",
                                        links=[{"kind": "supersedes", "to": "SR-001"}]))
    core = open_core(repo)
    assert judge.open_questions(core, SESSION) == []
    assert core.status(["SR-002"])["SR-002"].confirmation != "confirmed"
