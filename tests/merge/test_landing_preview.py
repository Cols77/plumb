"""report-683650f8 (SR-260, DEC-271; owner 2026-11-08): a landing holds only on new behaviour
left unproven or a real open owner decision. A branch's own check against the default branch
lists the proofs its landing will owe (the preview never holds the branch's check); only a
requirement whose behaviour the merge changes owes a proof; a question the merge holds on
travels with its options, so the landing session asks it once; a hidden-regression flag the
judge left standing is asked the same way, and the owner's "needed" ends it."""

from __future__ import annotations

from pathlib import Path

import pytest
from merge_helpers import commit, git, project, repin_all, write

from plumb import approvals
from plumb.api import open_core
from plumb.boundary import merge_report, render
from plumb.present import owner_text

pytestmark = pytest.mark.sr("SR-260")


def test_a_branch_checked_against_main_previews_the_proofs_its_landing_owes(repo: Path) -> None:
    project(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    commit(repo, "project")
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    repin_all(repo)
    commit(repo, "reorder add\n\nSR: SR-001")
    bare = merge_report(open_core(repo), "main", run_full=False)
    assert [(p["id"], p["why"]) for p in bare.proofs] == [("SR-001", "not shown working")]
    assert not bare.into_default
    text = "\n".join(render(bare))
    assert owner_text.PREMERGE_PROOFS_PREVIEW_HEADER.format(into="the default branch") in text
    assert owner_text.PREMERGE_PROOFS_HEADER.format(into="the default branch") not in text
    # the preview never holds: the exit is the one the same branch had with no delivery
    git(repo, "commit", "-q", "--amend", "-m", "reorder add")
    assert merge_report(open_core(repo), "main", run_full=False).exit == bare.exit


def test_only_changed_behaviour_owes_a_proof(repo: Path) -> None:
    """Owner 2026-11-08, "Only changed behaviour": SR-001's code changed, so it owes its
    proof; SR-002 is only named, by a commit touching nothing outside .plumb/, so it does not."""
    project(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    commit(repo, "project")
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    repin_all(repo)
    commit(repo, "reorder add\n\nSR: SR-001")
    write(repo, ".plumb/log/note.json", "{}\n")
    commit(repo, "a log entry naming a requirement\n\nSR: SR-002")
    report = merge_report(open_core(repo), "main", run_full=False)
    assert [p["id"] for p in report.proofs] == ["SR-001"]


def test_a_question_the_landing_holds_on_travels_with_its_options(repo: Path) -> None:
    """A judge question an ended session filed on SR-001 reaches the merge check with its
    text and options, so the session that lands asks it once through the question tool."""
    import json

    project(repo)
    core = open_core(repo)
    approvals.approve(core, ["SR-002", "INT-001"])
    commit(repo, "project")
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    repin_all(repo)
    commit(repo, "reorder add")
    asked = {"key": "which way?", "question": "Which way?", "job": "judge-old",
             "options": [{"label": "A (Recommended)", "description": "a"},
                         {"label": "B", "description": "b"}],
             "records": [{"id": "SR-001", "hash": open_core(repo).index()["SR-001"].hash}]}
    old = repo / ".plumb" / "session" / "old"
    old.mkdir(parents=True)
    (old / "judge_questions.json").write_text(json.dumps([asked]), encoding="utf-8")
    [row] = merge_report(open_core(repo), "main", run_full=False).questions
    assert row["options"] == asked["options"] and row["session"] == "old"
    assert row["question"] == "Which way?" and row["records"] == ["SR-001"]


def test_a_flag_the_judge_left_standing_is_asked_and_the_owners_needed_ends_it(
        repo: Path) -> None:
    from plumb.understand import testchange
    from plumb.understand.judge import answers_by_key

    project(repo)
    core = open_core(repo)
    judge = {"real": False, "verdict": "to_pass", "probability": 0.8, "reason": "deleted"}
    verification = {"failing": {"SR-001": [{
        "test": "tests/test_mod.py", "masked": True, "failing": True,
        "hidden_nodes": [{"node": "tests/test_mod.py::test_add", "requirements": ["SR-001"],
                          "judge": judge}]}]}}
    [row] = testchange.flag_questions(core, verification)
    assert row["records"] == ["SR-001"] and row["titles"] == ["add returns the sum"]
    assert row["options"][0]["label"] == testchange.NEEDED
    assert "made just to pass: deleted" in row["header"]
    pending = {**verification}
    pending["failing"]["SR-001"][0]["hidden_nodes"][0]["judge"] = {"real": False,
                                                                   "pending": True}
    assert testchange.flag_questions(core, pending) == []   # no verdict yet: nothing to ask
    node, srs = "tests/test_mod.py::test_add", ["SR-001"]
    assert not testchange.owner_needed(answers_by_key(core), node, srs)
    core.log_append_many("events", [("question-answer", {
        "question": row["question"], "answer": testchange.NEEDED, "via": "question-tool"})])
    assert testchange.owner_needed(answers_by_key(open_core(repo)), node, srs)
    core.log_append_many("events", [("question-answer", {
        "question": row["question"], "answer": testchange.RESTORE, "via": "question-tool"})])
    assert not testchange.owner_needed(answers_by_key(open_core(repo)), node, srs)
