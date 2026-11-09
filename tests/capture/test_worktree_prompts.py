"""SR-189: a worktree finds the main checkout's prompt log through git's common directory."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import log_prompt
from conftest import git

from iaso.api import open_core
from iaso.approvals import find_prompt
from iaso.understand.read import logged_prompt

pytestmark = pytest.mark.sr("SR-240")

WHOLE = "add a pow function. Also keep the old add function, and say so in the README"


@pytest.fixture
def worktree(repo: Path) -> Path:
    tree = repo.parent / "tree"
    git(repo, "worktree", "add", "-q", str(tree), "-b", "side")
    (tree / ".iaso").mkdir(exist_ok=True)
    return tree


def test_ex1_premise_is_the_whole_message_from_a_worktree(repo: Path, worktree: Path) -> None:
    digest = log_prompt(repo, WHOLE)
    assert logged_prompt(open_core(worktree), digest)["text"] == WHOLE


def test_ex2_capture_finds_the_prompt_without_copying_it(repo: Path, worktree: Path) -> None:
    digest = log_prompt(repo, WHOLE)
    assert find_prompt(open_core(worktree), digest)["text"] == WHOLE
    assert not (worktree / ".iaso" / "session" / "prompts.jsonl").exists()


def test_ex3_both_logs_are_read_and_the_latest_entry_wins(repo: Path, worktree: Path) -> None:
    log_prompt(repo, "only in main", at="2026-10-06T10:00:00Z")
    own = log_prompt(worktree, "only in the worktree")
    shared = log_prompt(repo, "same words", at="2026-10-06T10:00:00Z")
    log_prompt(worktree, "same words", at="2026-10-06T11:00:00Z")
    core = open_core(worktree)
    assert find_prompt(core, own)["text"] == "only in the worktree"
    assert find_prompt(core, shared)["at"] == "2026-10-06T11:00:00Z"
    assert find_prompt(core, log_prompt(repo, "only in main"))["text"] == "only in main"


def test_ex4_a_plain_checkout_reads_only_its_own_log(repo: Path) -> None:
    assert open_core(repo).paths.prompt_logs == [repo / ".iaso" / "session" / "prompts.jsonl"]
