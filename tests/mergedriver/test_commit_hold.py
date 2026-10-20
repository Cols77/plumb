"""R17's merge hold at every git entry point that records another line's work (sp6 10;
SR-077): the quick check judges what git will record, and it runs for a merge committed on
its own (pre-merge-commit), a merge finished by hand, git pull, and each rebase, cherry-pick
or revert step (prepare-commit-msg; the record merge driver stops those on an intent
conflict). One test per entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from mergedriver.mdhelpers import (
    THEIRS_STATEMENT,
    commit_all,
    ex,
    install_driver,
    make_repo,
    plumb,
    record,
    run_git,
    write_record,
)
from plumb import cli
from plumb.boundary.premerge import COMMIT_HOOK_MARKER, install_commit_hook, install_hook

SR = ".plumb/requirements/SR-005.md"
BASE = "A relay pins every stated record."
OURS = "A relay pins only what the owner affirms."


def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PLUMB_AGENT_SESSION"}
    env.update(PYTHONUTF8="1", GIT_EDITOR="true")
    return env


def _git(root: Path, *args: str, check: bool = False):
    return run_git(root, *args, check=check, env=_git_env())


def _adopted(path: Path) -> Path:
    root = make_repo(path)
    install_driver(root)
    install_hook(root, sys.executable)
    install_commit_hook(root, sys.executable)
    return root


def _diverged(tmp_path: Path, *, text_conflict: bool = False) -> Path:
    """main and feat-x both changed SR-005's statement (feat-x's version approved, so
    choosing it confirms it); with ``text_conflict`` both also changed notes.txt."""
    root = _adopted(tmp_path / "main")
    write_record(root, record(statement=BASE, examples=[ex(1)]))
    (root / "notes.txt").write_text("base\n", encoding="utf-8")
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    write_record(root, record(statement=OURS, examples=[ex(1)]))
    if text_conflict:
        (root / "notes.txt").write_text("main\n", encoding="utf-8")
    commit_all(root, "ours")
    write_record(other, record(statement=THEIRS_STATEMENT, examples=[ex(1)]))
    if text_conflict:
        (other / "notes.txt").write_text("feat\n", encoding="utf-8")
    from plumb.api import open_core
    from plumb.approvals import approve

    approve(open_core(other), ["SR-005"])
    # no SR trailer: SR-005 is touched by its record, and delivers nothing to prove (DEC-256)
    commit_all(other, "theirs")
    return root


def _head(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def _committed(root: Path, rev: str = "HEAD") -> str:
    return run_git(root, "show", f"{rev}:{SR}").stdout


def _relay_theirs(root: Path) -> None:
    """The owner chooses feat-x's version at their own terminal."""
    assert cli.main(["conflict", "choose", "IC-001", "--take", "theirs",
                     "--root", str(root)]) == 0


# --------------------------------------------------------------- the check reads the commit


@pytest.mark.sr("SR-260")
def test_template_steps_commit_the_choice(tmp_path: Path) -> None:
    """SR-077 EX-6, following the /plumb template exactly: the held merge, the relayed
    choice, then "finish the merge" (stage .plumb, the check, git commit). The merge commit
    carries the chosen record and its resolution entry; nothing is left behind."""
    root = _diverged(tmp_path)
    held = _git(root, "merge", "--no-edit", "feat-x")
    assert held.returncode != 0 and "IC-001" in held.stdout + held.stderr
    _relay_theirs(root)
    _git(root, "add", ".plumb", check=True)
    assert plumb(root, "merge-check", "--hook", "pre-merge-commit").returncode == 0
    done = _git(root, "commit", "-m", "Merge feat-x\n\nSR: SR-005")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "conflict:" not in _committed(root) and THEIRS_STATEMENT in _committed(root)
    # the resolution is an entry file of its own (sp6 6.1), committed with the merge
    assert run_git(root, "ls-tree", "-r", "--name-only", "HEAD", "--",
                   ".plumb/log/conflict-resolution").stdout.strip()
    assert run_git(root, "status", "--porcelain", "--untracked-files=all", "--",
                   ".plumb").stdout == ""


@pytest.mark.sr("SR-260")
def test_choice_left_unstaged_holds_the_commit(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug's own steps: the choice is written to the work tree but not staged, so the
    staged record still carries the block. The check holds (it judges what git will record)
    and git commit is refused; the merge stays in progress."""
    import plumb.mergedriver.conflicts as conflicts

    root = _diverged(tmp_path)
    _git(root, "merge", "--no-edit", "feat-x")
    monkeypatch.setattr(conflicts, "stage_choice", lambda *_a, **_k: None)
    _relay_theirs(root)
    head = _head(root)
    check = plumb(root, "merge-check", "--hook", "pre-merge-commit")
    assert check.returncode == 1
    assert f"{SR} is left out" in check.stdout and "finish the merge" in check.stdout
    refused = _git(root, "commit", "-m", "Merge feat-x\n\nSR: SR-005")
    assert refused.returncode != 0 and _head(root) == head
    assert run_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()


# --------------------------------------------------------------- merges finished by hand


@pytest.mark.sr("SR-260")
@pytest.mark.parametrize("how", ["text-conflict-then-commit", "no-commit-then-commit",
                                 "merge-continue"])
def test_merge_finished_by_hand_is_held(tmp_path: Path, how: str) -> None:
    """SR-077 EX-9: a merge git stops (a text conflict elsewhere, or --no-commit) and that is
    finished with git commit or git merge --continue is held on the open intent conflict."""
    root = _diverged(tmp_path, text_conflict=how != "no-commit-then-commit")
    head = _head(root)
    if how == "no-commit-then-commit":
        _git(root, "merge", "--no-commit", "feat-x")
    else:
        stopped = _git(root, "merge", "--no-edit", "feat-x")
        assert stopped.returncode != 0 and "notes.txt" in stopped.stdout
        (root / "notes.txt").write_text("both\n", encoding="utf-8")
        _git(root, "add", "notes.txt", check=True)
    if how == "merge-continue":
        finished = _git(root, "merge", "--continue")
    else:
        finished = _git(root, "commit", "-m", "Merge feat-x\n\nSR: SR-005")
    output = finished.stdout + finished.stderr
    assert finished.returncode != 0, output
    assert _head(root) == head
    assert "IC-001" in output and "/plumb conflicts" in output and "finish the merge" in output


@pytest.mark.sr("SR-260")
def test_merge_finished_by_hand_holds_unconfirmed(tmp_path: Path) -> None:
    """SR-077 EX-9: with no intent conflict, a merge finished by hand that touches a
    requirement not yet confirmed is held like one git commits on its own."""
    root = _adopted(tmp_path / "main")
    write_record(root, record(statement="s", examples=[ex(1)]))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    (root / "a.txt").write_text("main\n", encoding="utf-8")
    commit_all(root, "main side")
    write_record(other, record(statement="s2", examples=[ex(1)]))
    commit_all(other, "restate\n\nSR: SR-005")
    head = _head(root)
    _git(root, "merge", "--no-commit", "feat-x")
    finished = _git(root, "commit", "-m", "Merge feat-x\n\nSR: SR-005")
    assert finished.returncode != 0 and _head(root) == head
    assert '"relay checks" waits on a judge' in finished.stdout + finished.stderr


@pytest.mark.sr("SR-260")
def test_git_pull_is_held(tmp_path: Path) -> None:
    """SR-077 EX-9: git pull merges like git merge and is held the same way."""
    root = _diverged(tmp_path)
    head = _head(root)
    pulled = _git(root, "pull", "--no-rebase", "--no-edit", ".", "feat-x")
    assert pulled.returncode != 0 and _head(root) == head
    assert "IC-001" in pulled.stdout + pulled.stderr


@pytest.mark.sr("SR-260")
def test_hold_can_be_switched_off_for_one_commit(tmp_path: Path) -> None:
    """``git -c plumb.mergeHold=false commit`` records a merge the owner wants recorded as
    it is (prepare-commit-msg has no --no-verify)."""
    root = _diverged(tmp_path)
    _git(root, "merge", "--no-commit", "feat-x")
    done = _git(root, "-c", "plumb.mergeHold=false", "commit", "-m", "Merge feat-x")
    assert done.returncode == 0, done.stdout + done.stderr


# --------------------------------------------------------------- rebase, cherry-pick, revert


def _sequenced(tmp_path: Path, operation: str) -> tuple[Path, list[str], list[str]]:
    """``(worktree, start argv, continue argv)``: an operation whose step meets an intent
    conflict on SR-005."""
    root = _diverged(tmp_path)
    if operation == "rebase":
        return tmp_path / "feat", ["rebase", "main"], ["rebase", "--continue"]
    if operation == "cherry-pick":
        return root, ["cherry-pick", "feat-x"], ["cherry-pick", "--continue"]
    write_record(root, record(statement="A relay pins what the owner names.",
                              examples=[ex(1)]))
    commit_all(root, "restate again\n\nSR: SR-005")
    return root, ["revert", "--no-edit", "HEAD~1"], ["revert", "--continue"]


@pytest.mark.sr("SR-260")
@pytest.mark.parametrize("operation", ["rebase", "cherry-pick", "revert"])
def test_sequencer_step_stops_and_is_held(tmp_path: Path, operation: str) -> None:
    """SR-077 EX-10: the driver stops a rebase, cherry-pick or revert step on the intent
    conflict; continuing with the block still in the record is held; after the owner's
    choice the step continues and records the chosen version."""
    where, start, cont = _sequenced(tmp_path, operation)
    stopped = _git(where, *start)
    assert stopped.returncode != 0, stopped.stdout + stopped.stderr
    head = _head(where)  # a rebase has moved onto main; the step is not recorded
    assert "conflict:" in (where / SR).read_text(encoding="utf-8")
    _git(where, "add", SR, check=True)  # a careless "resolve": the block is still there
    held = _git(where, *cont)
    output = held.stdout + held.stderr
    assert held.returncode != 0, output
    assert "IC-001" in output and f"continue the {operation}" in output
    assert _head(where) == head
    assert cli.main(["conflict", "choose", "IC-001", "--take", "theirs",
                     "--root", str(where)]) == 0
    done = _git(where, *cont)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "conflict:" not in _committed(where)


@pytest.mark.sr("SR-260")
def test_ordinary_commit_skips_the_check(tmp_path: Path) -> None:
    """Outside a merge, rebase, cherry-pick or revert the hook's shell lines exit at once."""
    root = _adopted(tmp_path / "main")
    text = (root / ".git" / "hooks" / "prepare-commit-msg").read_text(encoding="utf-8")
    assert COMMIT_HOOK_MARKER in text and "MERGE_HEAD" in text
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", "a.txt", check=True)
    done = _git(root, "commit", "-m", "a")
    assert done.returncode == 0 and "plumb" not in done.stdout + done.stderr
