"""SR-216, SR-217, SR-218: the judge's waiting questions go away by themselves when they no longer
need the owner (a newer request, a gone branch, an approved record, a duplicate) and are settled
from a recorded decision; each is logged, approves nothing and is undone by ``question reopen``.
The model is stubbed."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest
from core.test_stale_resolve import LINK, REFORMATTED, _edit, project  # noqa: F401

from iaso import stale
from iaso.api import open_core
from iaso.contracts import DispatchError
from iaso.understand import cmd_question, judge, summary, tidy, worker
from understand.test_judge_job import SESSION, decision_text, log_prompt, requirement_text

SAYS = "A conflict may be answered through the agent in chat"
ASKED = "May a conflict be answered through the agent in chat?"
OTHER = "Can the agent relay a conflict answer in chat?"


def _ask(repo: Path, text: str = ASKED, *, job: str = "", at: str = "2026-11-01T10:00:00Z",
         branch: str | None = None, ids: tuple[str, ...] = ("SR-001",), session: str = SESSION
         ) -> str:
    core = open_core(repo)
    q = {"key": judge.question_key(text), "job": job or f"judge-{len(text)}",
         "records": [{"id": i, "hash": core.index()[i].hash} for i in ids],
         "principle": "", "blocking": False, "diagram": False, "question": text,
         "header": "Chat", "at": at,
         "options": [{"label": "Yes (Recommended)", "description": "Simpler."},
                     {"label": "No", "description": "Stricter."}]}
    if branch:
        q["branch"] = branch
    judge.add_question(core, session, q)
    return q["key"]


def _left(repo: Path) -> list[str]:
    return [str(q.get("question")) for q in judge.open_anywhere(open_core(repo))]


def _run(repo: Path, world: Any, script: Any) -> Any:
    core = open_core(repo)
    world.dispatcher.script = {"tidy": script}
    tidy.enqueue(core, SESSION)
    worker.run_once(core, SESSION)
    return core


def _decide(repo: Path, write_record, chosen: str, *, owner_said: bool = True) -> None:
    """DEC-900 choosing ``chosen``: it counts as the owner's recorded decision when their own
    logged words hold it (SR-335); otherwise only the agent proposed it."""
    write_record(repo, decision_text(900, "Does this need the owner?", chosen))
    if owner_said:
        log_prompt(repo, chosen)


def _withdrawn(repo: Path) -> list[Any]:
    return [e.payload for e in open_core(repo).events() if e.kind == "question-withdrawn"]


@pytest.fixture
def world(repo: Path, write_record, engine_standins):
    write_record(repo, requirement_text(1, "Chat answers", SAYS))
    return engine_standins


def _prompt(repo: Path, text: str, at: str) -> None:
    log_prompt(repo, text, at=at)


# -- SR-216 -----------------------------------------------------------------------------------

@pytest.mark.sr("SR-216")
def test_ex5_a_newer_request_naming_the_question_withdraws_it(repo: Path, world) -> None:
    key = _ask(repo)
    _prompt(repo, "Yes, answer conflicts through the agent in chat, no more asking", "2026-11-02T10:00:00Z")
    _run(repo, world, {"questions": [{"question": key, "replaced": True,
                                      "quote": "answer conflicts through the agent in chat"}]})
    assert _left(repo) == []
    (entry,) = _withdrawn(repo)
    assert entry["reason"] == "replaced" and "agent in chat" in entry["quote"]
    assert open_core(repo).status(["SR-001"])["SR-001"].confirmation == "proposed"  # EX-7


@pytest.mark.sr("SR-216")
def test_a_request_older_than_the_question_replaces_nothing(repo: Path, world) -> None:
    key = _ask(repo)
    _prompt(repo, "answer conflicts through the agent in chat", "2026-10-01T10:00:00Z")
    _run(repo, world, {"questions": [{"question": key, "replaced": True,
                                      "quote": "answer conflicts through the agent in chat"}]})
    assert _left(repo) == [ASKED] and _withdrawn(repo) == []


@pytest.mark.sr("SR-216")
def test_ex6_a_question_whose_branch_is_gone_is_not_listed(repo: Path, world) -> None:
    _ask(repo, branch="deleted-branch")
    assert _left(repo) == []


@pytest.mark.sr("SR-216")
def test_a_question_of_a_branch_that_exists_is_listed(repo: Path, world) -> None:
    _ask(repo, branch="main")
    assert _left(repo) == [ASKED]


@pytest.mark.sr("SR-216")
def test_ex1_repin_logs_the_withdrawal_of_the_stale_question(project: Path) -> None:  # noqa: F811
    from iaso import links

    _edit(project, REFORMATTED)
    stale.ask_owner(open_core(project), SESSION, link=LINK, record="SR-001", topic="Adds",
                    issue="the code changed", options=["keep", "undo"])
    links.unlink(open_core(project), LINK, "the code moved")
    (entry,) = _withdrawn(project)
    assert entry["reason"] == "link" and entry["link"] == LINK


def _merge_world(tmp_path: Path):
    from mergedriver.mdhelpers import commit_all, make_repo, run_git

    root = make_repo(tmp_path / "main")
    run_git(root, "checkout", "-q", "-b", "feat-x")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_all(root, "a")
    return root, run_git


@pytest.mark.sr("SR-216")
def test_ex10_merging_a_branch_withdraws_its_questions_and_logs_them(tmp_path: Path) -> None:
    from iaso.boundary.premerge import run_post_merge
    from understand.test_judge_job import SESSION as S

    root, run_git = _merge_world(tmp_path)
    for text in (ASKED, OTHER):
        judge.add_question(open_core(root), S, {"key": judge.question_key(text), "job": f"j{len(text)}",
                                                "records": [], "question": text,
                                                "branch": "feat-x", "options": []})
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "feat-x")
    assert run_post_merge(root) == 0
    assert [e["reason"] for e in _withdrawn(root)] == ["branch", "branch"]
    assert judge.unanswered(open_core(root), S) == []


@pytest.mark.sr("SR-216")
def test_ex11_syncing_main_into_a_feature_branch_withdraws_nothing(tmp_path: Path) -> None:
    from mergedriver.mdhelpers import commit_all, run_git
    from iaso.boundary.premerge import run_post_merge

    root, _ = _merge_world(tmp_path)
    run_git(root, "checkout", "-q", "main")
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    commit_all(root, "b")
    judge.add_question(open_core(root), SESSION, {"key": "k", "job": "j", "records": [],
                                                  "question": "q", "branch": "main", "options": []})
    run_git(root, "checkout", "-q", "feat-x")
    run_git(root, "merge", "-q", "--no-ff", "--no-verify", "-m", "sync", "main")
    assert run_post_merge(root) == 0
    assert _withdrawn(root) == []


@pytest.mark.sr("SR-216")
def test_ex12_a_branch_not_yet_merged_keeps_its_questions(tmp_path: Path) -> None:
    from mergedriver.mdhelpers import commit_all, run_git
    from iaso.boundary.premerge import run_post_merge

    root, _ = _merge_world(tmp_path)
    run_git(root, "checkout", "-q", "main")
    judge.add_question(open_core(root), SESSION, {"key": "k", "job": "j", "records": [],
                                                  "question": "q", "branch": "feat-x",
                                                  "options": []})
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    commit_all(root, "b")
    run_git(root, "merge", "-q", "--no-verify", "HEAD")
    assert run_post_merge(root) == 0
    assert _withdrawn(root) == [] and judge.unanswered(open_core(root), SESSION)


# -- SR-218 -----------------------------------------------------------------------------------

@pytest.mark.sr("SR-218")
def test_ex1_an_approved_record_that_answers_withdraws_the_question_quoting_it(
        repo: Path, world, write_record) -> None:
    key = _ask(repo)
    _decide(repo, write_record, SAYS)
    _run(repo, world, {"questions": [{"question": key, "record": "DEC-900",
                                      "quote": "through the agent in chat"}]})
    assert _left(repo) == []
    (bound,) = [e for e in open_core(repo).events() if e.kind == "answer-bound"]
    assert bound.payload["record"] == "DEC-900" and "agent in chat" in bound.payload["quote"]


@pytest.mark.sr("SR-218")
def test_ex2_a_proposed_record_answers_nothing(repo: Path, world, write_record) -> None:
    key = _ask(repo)
    _decide(repo, write_record, SAYS, owner_said=False)
    _run(repo, world, {"questions": [{"question": key, "record": "DEC-900",
                                      "quote": "through the agent in chat"}]})
    assert _left(repo) == [ASKED]


@pytest.mark.sr("SR-218")
def test_ex3_a_question_repeating_another_is_withdrawn_naming_the_other(repo: Path, world) -> None:
    key, other = _ask(repo), _ask(repo, OTHER)
    _run(repo, world, {"questions": [{"question": other, "other": key}]})
    assert _left(repo) == [ASKED]
    (entry,) = _withdrawn(repo)
    assert entry["reason"] == "duplicate" and entry["other"] == key


@pytest.mark.sr("SR-218")
def test_a_duplicate_naming_a_question_that_is_not_waiting_withdraws_nothing(
        repo: Path, world) -> None:
    key = _ask(repo)
    _run(repo, world, {"questions": [{"question": key, "other": "no such question"}]})
    assert _left(repo) == [ASKED]


@pytest.mark.sr("SR-218")
def test_ex4_a_judge_that_cannot_be_reached_withdraws_nothing_and_prints_nothing(
        repo: Path, world) -> None:
    key = _ask(repo)
    core = _run(repo, world, DispatchError("run", "the model could not be reached"))
    assert _left(repo) == [ASKED] and _withdrawn(repo) == []
    assert summary.owner_line(core, SESSION) == ""
    del key


@pytest.mark.sr("SR-218")
def test_ex5_an_unsure_judge_keeps_the_question(repo: Path, world) -> None:
    _ask(repo)
    _run(repo, world, {"questions": []})
    assert _left(repo) == [ASKED] and _withdrawn(repo) == []


@pytest.mark.sr("SR-218")
def test_reopen_undoes_a_duplicate_withdrawal(repo: Path, world) -> None:
    key, other = _ask(repo), _ask(repo, OTHER)
    _run(repo, world, {"questions": [{"question": other, "other": key}]})
    assert cmd_question.run("question", ["--root", str(repo), "--session", SESSION,
                                         "reopen", OTHER[:20]]) == 0
    assert sorted(_left(repo)) == sorted([ASKED, OTHER])


# -- SR-217: settled from a recorded decision -------------------------------------------------

DECIDED = "Reformatting never needs the owner"


def _stale_question(project: Path, write_record, owned: bool = True) -> str:
    _edit(project, REFORMATTED)
    _decide(project, write_record, DECIDED, owner_said=owned)
    core = open_core(project)
    stale.ask_owner(core, SESSION, link=LINK, record="SR-001", topic="Adds numbers",
                    issue="the code was reformatted", options=["keep", "undo"])
    (q,) = judge.open_anywhere(open_core(project))
    return str(q["key"])


def _link_state(project: Path) -> str:
    (state,) = open_core(project).link_states(["SR-001"])
    return state.state


@pytest.mark.sr("SR-217")
def test_ex1_a_decision_that_settles_a_stale_link_question_refreshes_the_link(
        project: Path, write_record, engine_standins) -> None:  # noqa: F811
    key = _stale_question(project, write_record)
    assert _link_state(project) == "stale"
    _run(project, engine_standins, {"questions": [], "settlements": [
        {"question": key, "action": "repin", "decision": "DEC-900", "quote": DECIDED}]})
    assert _link_state(project) == "current" and _left(project) == []
    settled = [e for e in _withdrawn(project) if e["reason"] == "settled"]
    assert settled[0]["decision"] == "DEC-900" and settled[0]["quote"] == DECIDED


@pytest.mark.sr("SR-217")
def test_a_decision_may_reword_the_requirement_it_settles(
        project: Path, write_record, engine_standins) -> None:  # noqa: F811
    key = _stale_question(project, write_record)
    _run(project, engine_standins, {"questions": [], "settlements": [
        {"question": key, "action": "reword", "decision": "DEC-900", "quote": DECIDED,
         "wording": "add returns the sum of its two numbers."}]})
    assert "sum of its two numbers" in str(open_core(project).index()["SR-001"].fields["statement"])
    assert _link_state(project) == "current"


@pytest.mark.sr("SR-217")
def test_a_proposed_decision_or_a_misquote_settles_nothing(
        project: Path, write_record, engine_standins) -> None:  # noqa: F811
    key = _stale_question(project, write_record, owned=False)
    settle = {"question": key, "action": "repin", "decision": "DEC-900", "quote": DECIDED}
    _run(project, engine_standins, {"questions": [], "settlements": [settle]})
    log_prompt(project, DECIDED)        # now the owner said it, but the quote is not in it
    _run(project, engine_standins, {"questions": [], "settlements": [
        {**settle, "quote": "the owner is never asked"}]})
    assert _link_state(project) == "stale" and len(_left(project)) == 1


@pytest.mark.sr("SR-217")
def test_ex5_reopen_puts_back_what_a_settlement_changed(
        project: Path, write_record, engine_standins) -> None:  # noqa: F811
    key = _stale_question(project, write_record)
    before = str(open_core(project).index()["SR-001"].fields["statement"])
    _run(project, engine_standins, {"questions": [], "settlements": [
        {"question": key, "action": "reword", "decision": "DEC-900", "quote": DECIDED,
         "wording": "add returns the sum of its two numbers."}]})
    assert cmd_question.run("question", ["--root", str(project), "--session", SESSION,
                                         "reopen", key[:20]]) == 0
    assert str(open_core(project).index()["SR-001"].fields["statement"]) == before
    assert _link_state(project) == "stale" and len(_left(project)) == 1


@pytest.mark.sr("SR-216")
def test_ex6_a_squash_merged_branch_is_gone_once_deleted_not_before(tmp_path: Path) -> None:
    root, run_git = _merge_world(tmp_path)
    judge.add_question(open_core(root), SESSION, {"key": "k", "job": "j", "records": [],
                                                  "question": "q", "branch": "feat-x",
                                                  "options": []})
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "-q", "--squash", "--no-verify", "feat-x")
    run_git(root, "commit", "-q", "--no-verify", "-m", "squash")
    assert [q["key"] for q in judge.unanswered(open_core(root), SESSION)] == ["k"]
    run_git(root, "branch", "-q", "-D", "feat-x")
    assert judge.unanswered(open_core(root), SESSION) == []


@pytest.mark.sr("SR-216")
def test_ex6_one_git_call_checks_every_branch_and_none_when_no_question_has_one(
        repo: Path, world, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    real = judge._git
    monkeypatch.setattr(judge, "_git", lambda root, *a: calls.append(a) or real(root, *a))
    _ask(repo)
    _ask(repo, OTHER, branch="main")
    calls.clear()
    judge.unanswered(open_core(repo), SESSION)
    assert [c[0] for c in calls] == ["for-each-ref"]
    calls.clear()
    judge.add_question(open_core(repo), SESSION, {"key": "x", "job": "x", "records": [],
                                                  "question": "x", "options": []})
    assert [c[0] for c in calls].count("symbolic-ref") == 1


@pytest.mark.sr("SR-217")
def test_ex2_a_record_a_decision_contradicts_is_reworded_citing_it_and_reopen_undoes_it(
        repo: Path, world, write_record) -> None:
    """SR-217 EX-2: a question about a confirmed record the owner's decision contradicts is not
    asked; the record is reworded (an unconfirmed edit the judge validates), logged with the
    decision."""
    key = _ask(repo)
    _decide(repo, write_record, DECIDED)
    before = str(open_core(repo).index()["SR-001"].fields["statement"])
    wording = "A conflict is never answered through the agent in chat."
    settle = {"question": key, "action": "reword", "decision": "DEC-900", "quote": DECIDED,
              "record": "SR-001", "wording": wording}
    _run(repo, world, {"questions": [], "settlements": [{**settle, "record": "DEC-900"}]})
    assert _left(repo) == [ASKED]       # the decision itself is never the one reworded
    log_prompt(repo, "carry on")        # new inputs: a new job
    _run(repo, world, {"questions": [], "settlements": [settle]})
    assert _left(repo) == []
    assert str(open_core(repo).index()["SR-001"].fields["statement"]) == wording
    (event,) = [e for e in _withdrawn(repo) if e["reason"] == "settled"]
    assert event["decision"] == "DEC-900" and event["quote"] == DECIDED
    assert cmd_question.run("question", ["--root", str(repo), "--session", SESSION,
                                         "reopen", key[:20]]) == 0
    assert str(open_core(repo).index()["SR-001"].fields["statement"]) == before
    assert _left(repo) == [ASKED]


@pytest.mark.sr("SR-217")
def test_ex4_no_judge_reached_is_said_once_and_settles_nothing(repo: Path, world) -> None:
    from iaso.understand import files

    _ask(repo)
    notes = files.session_dir(repo, SESSION) / "agent_notes.json"
    for _ in range(2):
        _run(repo, world, DispatchError("run", "the model could not be reached"))
    assert files.read_json(notes).count(tidy.UNREACHABLE) == 1
    assert _left(repo) == [ASKED] and _withdrawn(repo) == []
