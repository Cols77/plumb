"""SR-384: in an adopted repository's main checkout the pre-tool hook refuses an agent's writes
(edit tools, writing shell commands, git commit outside a merge, plumb's record writers) and
tells it to work on a branch in a worktree; worktrees, reads, ignored files and paths outside
the repository stay open, and the end-of-turn hook holds no stale link there."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import git
from host.test_stop_stale import (  # noqa: F401 - fixtures
    CHANGED,
    _block,
    edit,
    judge_reachable_tests_fail,
    project,
    run_stop,
    start_turn,
)

from plumb.hosts.claude_code import pretool

pytestmark = [pytest.mark.sr("SR-384"), pytest.mark.main_guard]


@pytest.fixture
def main(repo: Path) -> Path:
    (repo / ".gitignore").write_text("scratch/\n.plumb/wt/\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "app")
    return repo


@pytest.fixture
def worktree(main: Path, tmp_path: Path) -> Path:
    path = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "feature", str(path))
    return path


def call(cwd: Path, tool: str, **tool_input: str) -> dict:
    root = cwd
    return pretool.decide(root, "s1", tool, tool_input, {"cwd": str(cwd)})


def bash(root: Path, command: str, cwd: Path | None = None) -> dict:
    return pretool.decide(root, "s1", "Bash", {"command": command},
                          {"cwd": str(cwd or root)})


def refused(answer: dict) -> bool:
    out = answer.get("hookSpecificOutput", {})
    return out.get("permissionDecision") == "deny" and "worktree" in out["permissionDecisionReason"]


def test_ex1_an_edit_tool_in_mains_checkout_is_refused_naming_a_worktree(main: Path) -> None:
    edit_call = {"file_path": str(main / "src" / "app.py"), "old_string": "1", "new_string": "2"}
    assert refused(pretool.decide(main, "s1", "Edit", edit_call, {"cwd": str(main)}))
    rel = {"file_path": "src/new.py", "content": "y\n"}
    assert refused(pretool.decide(main, "s1", "Write", rel, {"cwd": str(main)}))


def test_ex2_a_command_that_changes_into_a_worktree_goes_ahead(main: Path,
                                                               worktree: Path) -> None:
    command = f"cd {worktree} && echo y > src/app.py && git add -A && git commit -qm x"
    assert bash(main, command) == {}
    edit_call = {"file_path": str(worktree / "src" / "app.py"), "old_string": "1",
                 "new_string": "2"}
    assert pretool.decide(main, "s1", "Edit", edit_call, {"cwd": str(main)}) == {}
    assert pretool.decide(worktree, "s1", "Edit", edit_call, {"cwd": str(worktree)}) == {}


def test_ex2_a_commit_in_a_worktree_is_not_refused(main: Path, worktree: Path) -> None:
    assert bash(worktree, "git commit -qm x") == {}
    assert bash(main, f"cd {worktree} && git commit -qm x") == {}


def test_ex3_a_redirect_git_add_or_plumb_capture_is_refused(main: Path) -> None:
    assert refused(bash(main, "echo y > src/app.py"))
    assert refused(bash(main, "echo y >> src/app.py"))
    assert refused(bash(main, "printf y | tee src/app.py"))
    assert refused(bash(main, "git add -A"))
    assert refused(bash(main, "uv run --no-sync plumb capture --stdin"))
    assert refused(bash(main, "plumb link SR-001 implemented_by src/app.py"))
    assert refused(bash(main, "sed -i s/1/2/ src/app.py"))
    assert refused(bash(main, "rm src/app.py"))
    assert refused(bash(main, "touch src/new.py"))
    assert refused(bash(main, "cd src && mkdir pkg"))


def test_ex4_git_commit_is_refused_unless_a_merge_is_in_progress(main: Path) -> None:
    assert refused(bash(main, "git commit -m x"))
    git(main, "checkout", "-q", "-b", "side")
    (main / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    git(main, "commit", "-qam", "side")
    git(main, "checkout", "-q", "main")
    git(main, "merge", "--no-commit", "--no-ff", "side")
    assert bash(main, "git commit -m merged") == {}
    git(main, "merge", "--abort")
    assert refused(bash(main, "git commit -m x"))


def test_ex5_reads_tests_merges_and_scratch_files_go_ahead(main: Path, tmp_path: Path) -> None:
    (main / "scratch").mkdir()
    for command in ("cat src/app.py", "git status", "git log -1", "git diff",
                    "uv run --no-sync plumb status", "uv run --no-sync plumb tests run",
                    "git merge feature", "git merge --abort", "git checkout -- src/app.py",
                    "git worktree list", "git branch -a", "grep -n x src/app.py 2>/dev/null",
                    "rm -rf scratch/x", f"echo y > {tmp_path}/out.txt",
                    "echo y > scratch/out.txt", "echo y > /dev/null 2>&1", "mkdir -p /tmp/zz-sr384",
                    "plumb show SR-001"):
        assert bash(main, command) == {}, command
    edit_call = {"file_path": str(main / "scratch" / "a.txt"), "content": "y"}
    assert call(main, "Write", **edit_call) == {}
    outside = {"file_path": str(tmp_path / "elsewhere.txt"), "content": "y"}
    assert call(main, "Write", **outside) == {}
    nested = main / ".plumb" / "wt" / "x"
    nested.mkdir(parents=True)
    git(main, "worktree", "add", "-q", "-b", "nested", str(nested))
    inside = {"file_path": str(nested / "src" / "app.py"), "content": "y"}
    assert call(main, "Write", **inside) == {}


def test_a_redirect_to_tmp_is_allowed(main: Path) -> None:
    assert bash(main, "echo y > /tmp/sr384-scratch.txt") == {}


def test_ex6_guard_main_false_turns_the_guard_off(main: Path) -> None:
    config = main / ".plumb" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "\nmerge:\n  guard_main: false\n",
                      encoding="utf-8")
    edit_call = {"file_path": str(main / "src" / "app.py"), "old_string": "1", "new_string": "2"}
    assert pretool.decide(main, "s1", "Edit", edit_call, {"cwd": str(main)}) == {}
    assert bash(main, "git add -A") == {}


def test_ex7_the_owner_by_hand_never_meets_the_guard(main: Path) -> None:
    """The owner's terminal runs no hook, and plumb installs no git hook for this guard."""
    (main / "src" / "app.py").write_text("x = 3\n", encoding="utf-8")
    git(main, "commit", "-qam", "owner edit")
    hooks = subprocess.run(["git", "-C", str(main), "rev-parse", "--git-path", "hooks"],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert not any("guard_main" in p.read_text(encoding="utf-8", errors="ignore")
                   for p in (main / hooks).glob("*") if p.is_file())


def test_the_guard_never_fails_a_call(main: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import main_guard

    def boom(*args: object) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(main_guard, "main_checkout", boom)
    assert bash(main, "git add -A") == {}


def test_ex8_the_stop_hook_does_not_hold_for_a_stale_link_in_mains_checkout(
        project: Path, hook_input) -> None:  # noqa: F811
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    assert _block(run_stop(project, hook_input)) is None
    git(project, "checkout", "-q", "-b", "side")   # control: on a branch the hold applies
    start_turn(project, turn_id="turn-2")
    edit(project, "src/calc.py", "def add(a, b):\n    return a + b + 0\n")
    assert _block(run_stop(project, hook_input)) is not None
