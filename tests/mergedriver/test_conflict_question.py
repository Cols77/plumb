"""Case report-cee7804c: a conflict a merge left in a worktree is settled by the owner's
question-tool answer, applied in that worktree even when the session's hook runs in main."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from mergedriver.mdhelpers import (
    THEIRS_STATEMENT,
    conflicted,
    events,
    make_repo,
    parse,
    run_git,
)

from iaso.api import open_core
from iaso.hosts.claude_code import question_answer
from iaso.mergedriver import conflicts, open_conflicts

pytestmark = pytest.mark.sr("SR-211")
SR = ".iaso/requirements/SR-005.md"


@pytest.fixture
def held(tmp_path: Path) -> tuple[Path, Path, dict]:
    """main, and a worktree whose SR-005 holds a conflict; the question asked there."""
    root = make_repo(tmp_path / "main")
    feat = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(feat))
    conflicted(feat)
    return root, feat, conflicts.ask(open_core(feat), "IC-001", "worktree-session")


def _answer(root: Path, hook_input, asked: dict, answer: str) -> None:
    question = asked["questions"][0]["question"]
    payload = hook_input("PostToolUse", tool_name="AskUserQuestion", tool_input=asked,
                         tool_response={"answers": {question: answer}})
    assert question_answer.main(stdin=io.StringIO(payload), stdout=io.StringIO(),
                                root=root) == 0


def test_the_answer_heard_in_main_settles_the_worktrees_conflict(held, hook_input) -> None:
    root, feat, asked = held
    assert [o["label"] for o in asked["questions"][0]["options"]] == [
        "Keep main's version", "Keep feat-x's version", "Both"]
    _answer(root, hook_input, asked, "Keep feat-x's version")
    data = parse((feat / SR).read_text(encoding="utf-8"))[0]
    assert data["statement"] == THEIRS_STATEMENT and "conflict" not in data
    (entry,) = events(feat, "conflict-resolution")
    assert (entry["ic"], entry["take"], entry["by"]) == ("IC-001", "theirs", "owner")
    assert conflicts.pending(feat, "worktree-session") == []
    assert events(root, "conflict-resolution") == []


def test_the_owners_own_words_choose_nothing(held, hook_input) -> None:
    root, feat, asked = held
    _answer(root, hook_input, asked, "Both")      # no combined version is proposed
    assert len(open_conflicts(open_core(feat))) == 1
    asked = conflicts.ask(open_core(feat), "IC-001", "worktree-session")
    _answer(root, hook_input, asked, "let me think about it")
    assert len(open_conflicts(open_core(feat))) == 1
    assert events(feat, "conflict-resolution") == []


def test_a_pending_entry_cannot_point_another_question_at_the_conflict(held, hook_input) -> None:
    root, feat, asked = held
    other = {"questions": [{**asked["questions"][0], "question": "Which colour?"}]}
    from iaso.understand import files
    from iaso.understand.judge import question_key

    files.write_json_atomic(
        files.session_dir(feat, "worktree-session") / conflicts.QUESTIONS_FILE,
        [{"key": question_key("Which colour?"), "ic": "IC-001"}])
    _answer(root, hook_input, other, "Keep feat-x's version")
    assert len(open_conflicts(open_core(feat))) == 1
