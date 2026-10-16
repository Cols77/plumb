"""R17's merge hold when git would FAST-FORWARD the default branch (SR-077 EX-13): a
fast-forward records no merge commit, so git runs no pre-merge-commit hook. The one choke
point, installed by /plumb init with the other merge hooks (``premerge.ff_hold`` and the
post-merge hook), keeps every way in held. One test per entry point: a plain ``git merge``
that would fast-forward, a ``git pull`` that would, and ``--ff-only`` (merge and pull)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mergedriver.mdhelpers import commit_all, ex, make_repo, record, run_git, write_record
from plumb import cli
from plumb.boundary.premerge import NO_FF


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PLUMB_AGENT_SESSION"}
    env.update(PYTHONUTF8="1", GIT_EDITOR="true")
    return env


def _git(root: Path, *args: str):
    return run_git(root, *args, check=False, env=_env())


def _head(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def _adopted(tmp_path: Path) -> tuple[Path, Path]:
    """``/plumb init`` in a repository holding SR-005, and a worktree on feat-x; main has
    not moved since, so merging feat-x into main would fast-forward."""
    root = make_repo(tmp_path / "main")
    assert cli.main(["init", "--root", str(root)]) == 0
    write_record(root, record(statement="A relay pins every stated record.", examples=[ex(1)]))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    return root, other


def _held_work(other: Path) -> None:
    """feat-x changes the unconfirmed SR-005 and adds a file it does not declare."""
    write_record(other, record(statement="A relay pins only what the owner affirms.",
                               examples=[ex(1)]))
    (other / "src").mkdir()
    (other / "src" / "relay.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(other, "relay\n\nSR: SR-005")


def _assert_not_recorded(root: Path, before: str, output: str) -> None:
    assert _head(root) == before, output
    assert 'SR-005 "relay checks" is not confirmed yet' in output
    assert "no test run" in output


@pytest.mark.sr("SR-260")
def test_init_makes_merges_into_main_record_a_merge_commit(tmp_path: Path) -> None:
    root, _ = _adopted(tmp_path)
    assert NO_FF in run_git(root, "config", "--get", "branch.main.mergeoptions").stdout
    assert (root / ".git" / "hooks" / "post-merge").exists()
    assert cli.main(["hooks", "uninstall", "--root", str(root)]) == 0
    assert run_git(root, "config", "--get", "branch.main.mergeoptions",
                   check=False).stdout.strip() == ""
    assert not (root / ".git" / "hooks" / "post-merge").exists()


@pytest.mark.sr("SR-260")
def test_plain_merge_that_would_fast_forward_is_held(tmp_path: Path) -> None:
    """SR-077 EX-13: ``git merge feat-x`` with main not moved: a merge commit is prepared
    and the quick check holds it; main does not move."""
    root, other = _adopted(tmp_path)
    _held_work(other)
    before = _head(root)
    merged = _git(root, "merge", "--no-edit", "feat-x")
    output = merged.stdout + merged.stderr
    assert merged.returncode != 0, output
    _assert_not_recorded(root, before, output)
    assert run_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()
    assert "finish the merge" in output


@pytest.mark.sr("SR-260")
def test_pull_that_would_fast_forward_is_held(tmp_path: Path) -> None:
    """SR-077 EX-13: ``git pull`` of feat-x into main, which would fast-forward."""
    root, other = _adopted(tmp_path)
    _held_work(other)
    before = _head(root)
    pulled = _git(root, "pull", "--no-rebase", "--no-edit", ".", "feat-x")
    output = pulled.stdout + pulled.stderr
    assert pulled.returncode != 0, output
    _assert_not_recorded(root, before, output)


@pytest.mark.sr("SR-260")
@pytest.mark.parametrize("command", [["merge", "--ff-only", "feat-x"],
                                     ["pull", "--ff-only", ".", "feat-x"]])
def test_ff_only_is_put_back(tmp_path: Path, command: list[str]) -> None:
    """SR-077 EX-13: an explicit fast-forward (``--ff-only``, which no merge option
    overrides) is checked by the post-merge hook and main is put back where it was: nothing
    held stays recorded, the work tree is clean, and the owner is told how to bring it in."""
    root, other = _adopted(tmp_path)
    _held_work(other)
    (root / "local.txt").write_text("uncommitted\n", encoding="utf-8")
    before = _head(root)
    done = _git(root, *command)
    output = done.stdout + done.stderr
    _assert_not_recorded(root, before, output)
    assert not (root / "src" / "relay.py").exists()
    assert (root / "local.txt").read_text(encoding="utf-8") == "uncommitted\n"
    assert "main was put back where it was" in output
    assert 'say "merge feat-x"' in output
    status = run_git(root, "status", "--porcelain").stdout
    assert status.strip() == "?? local.txt"


@pytest.mark.sr("SR-260")
def test_clean_fast_forward_stays(tmp_path: Path) -> None:
    """A fast-forward the check does not hold keeps git's own result."""
    root, other = _adopted(tmp_path)
    (other / "notes.txt").write_text("notes\n", encoding="utf-8")
    after = commit_all(other, "notes")
    done = _git(root, "merge", "--ff-only", "feat-x")
    assert _head(root) == after, done.stdout + done.stderr
    assert "nothing holds this merge" in done.stdout + done.stderr


@pytest.mark.sr("SR-260")
def test_owner_option_kept_and_hold_switch(tmp_path: Path) -> None:
    """An owner's own fast-forward option stays (the post-merge hook still checks), and
    ``plumb.mergeHold=false`` lets a fast-forward through."""
    root = make_repo(tmp_path / "own")
    run_git(root, "config", "branch.main.mergeoptions", "--ff-only")
    assert cli.main(["init", "--root", str(root)]) == 0
    assert run_git(root, "config", "--get", "branch.main.mergeoptions").stdout.strip() \
        == "--ff-only"
    write_record(root, record(statement="s", examples=[ex(1)]))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    _held_work(other)
    run_git(root, "config", "plumb.mergeHold", "false")
    after = run_git(root, "rev-parse", "feat-x").stdout.strip()
    _git(root, "merge", "feat-x")
    assert _head(root) == after
