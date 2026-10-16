"""R17: a merged branch is changing nothing, even while its worktree stays on disk, idle,
with the list its last session published before the commit (SR-079 EX-5). One test per
reader: the session-start brief, the prompt delta, the stop hook's overlap lines, ``plumb
status`` and the status line."""

from __future__ import annotations

from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement, run_git
from plumb import awareness
from plumb.api import open_core
from plumb.awareness import publish as pub
from plumb.awareness.turn import at_session_start, at_stop

LINE = 'plumb: SR-005 "relay checks" is also being changed on branch feat-x'


def _edit(root: Path, statement: str) -> None:
    requirement(root, "SR-005", "relay checks", statement)
    pub.publish(open_core(root), [".plumb/requirements/SR-005.md"])


def _idle_merged(tmp_path: Path, *, merge: bool = True) -> Path:
    """feat-x's session edited SR-005 and published it as pending; the edit was then
    committed with no session to publish again, and main merged feat-x. A later worktree
    on feat-y works on SR-005; returns its root."""
    main = make_repo(tmp_path / "main")
    requirement(main, "SR-005", "relay checks", "A relay pins every stated record.")
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    _edit(other, "A relay pins the stated group, named by its title.")
    assert ".plumb/requirements/SR-005.md" in (pub.read_changing(pub.changing_path(other))
                                               or {}).get("pending", [])
    commit_all(other, "relay group")       # the stop hook does not run again
    if merge:
        run_git(main, "merge", "-q", "--no-edit", "feat-x")
        assert run_git(main, "merge-base", "--is-ancestor", "feat-x", "main",
                       check=False) == ""
    mine = add_worktree(main, tmp_path / "wt-y", "feat-y")
    _edit(mine, "A relay pins only the records the owner's words affirm.")
    return mine


@pytest.mark.sr("SR-258")
def test_unmerged_committed_worktree_still_shows(tmp_path: Path) -> None:
    """Control: until the default branch holds it, the committed work is still in flight."""
    mine = _idle_merged(tmp_path, merge=False)
    assert awareness.delta_lines(open_core(mine), ["SR-005"])[0].text == LINE


@pytest.mark.sr("SR-258")
def test_session_start_brief_drops_merged_idle_worktree(tmp_path: Path) -> None:
    mine = _idle_merged(tmp_path)
    core = open_core(mine)
    assert [line.text for line in at_session_start(core)] == []
    assert awareness.brief_lines(open_core(mine)) == []


@pytest.mark.sr("SR-258")
def test_prompt_delta_drops_merged_idle_worktree(tmp_path: Path) -> None:
    mine = _idle_merged(tmp_path)
    assert awareness.delta_lines(open_core(mine), ["SR-005"]) == []


@pytest.mark.sr("SR-258")
def test_stop_overlap_drops_merged_idle_worktree(tmp_path: Path) -> None:
    mine = _idle_merged(tmp_path)
    lines = at_stop(open_core(mine), [".plumb/requirements/SR-005.md"], ["SR-005"])
    assert [line.text for line in lines] == []


@pytest.mark.sr("SR-258")
def test_plumb_status_drops_merged_idle_worktree(tmp_path: Path) -> None:
    mine = _idle_merged(tmp_path)
    lines = awareness.status_section(open_core(mine))
    assert not any("feat-x" in line for line in lines), lines


@pytest.mark.sr("SR-258")
def test_status_line_drops_merged_idle_worktree(tmp_path: Path) -> None:
    mine = _idle_merged(tmp_path)
    assert awareness.snapshot_fields(open_core(mine), ["SR-005"]) == {}
