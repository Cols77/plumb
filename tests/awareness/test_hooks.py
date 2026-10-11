"""The four hooks carry awareness (sp6 9.2, 9.4): two real worktrees, the real handlers."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement
from plumb.awareness import publish as pub
from plumb.hosts.claude_code import post_edit, prompt, session_start, stop

pytestmark = pytest.mark.sr("SR-078")


def _call(module, root: Path, payload: str, **kwargs) -> str:  # noqa: ANN001
    out = io.StringIO()
    module.main(stdin=io.StringIO(payload), stdout=out, root=root, **kwargs)
    return out.getvalue()


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    main = make_repo(tmp_path / "main")
    requirement(main, "SR-005", "relay checks", "A relay pins every stated record.")
    requirement(main, "SR-006", "status card")
    commit_all(main, "records")
    other = add_worktree(main, tmp_path / "wt-x", "feat-x")
    return main, other


def _edit_with_hooks(root: Path, hook_input, statement: str,  # noqa: ANN001
                     ask: str = "change the relay checks") -> dict:
    _call(prompt, root, hook_input("UserPromptSubmit", prompt=ask), backend=None)
    path = root / ".plumb" / "requirements" / "SR-005.md"
    requirement(root, "SR-005", "relay checks", statement)
    _call(post_edit, root, hook_input("PostToolUse", tool_name="Edit",
                                      tool_input={"file_path": str(path)}))
    out = _call(stop, root, hook_input("Stop"), verify=None, unjudged=None)
    return json.loads(out) if out.strip() else {}


def test_session_start_brief_names_the_overlap(tmp_path: Path, hook_input) -> None:  # noqa: ANN001
    main, other = _pair(tmp_path)
    _edit_with_hooks(other, hook_input, "feat-x: pins the stated group")
    requirement(main, "SR-005", "relay checks", "main: pins only the affirmed records")
    pub.publish(__import__("plumb.api", fromlist=["open_core"]).open_core(main),
                [".plumb/requirements/SR-005.md"])
    out = _call(session_start, main, hook_input("SessionStart"), verify=None)
    assert 'plumb: SR-005 "relay checks" is also being changed on branch feat-x' in out
    status = json.loads((main / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert status["overlaps"] == 1 and status["overlap_labels"] == ["feat-x"]


def test_post_edit_publishes_the_path_before_the_turn_ends(tmp_path: Path,
                                                          hook_input) -> None:  # noqa: ANN001
    _main, other = _pair(tmp_path)
    path = other / ".plumb" / "requirements" / "SR-005.md"
    requirement(other, "SR-005", "relay checks", "edited")
    _call(post_edit, other, hook_input("PostToolUse", tool_name="Edit",
                                       tool_input={"file_path": str(path)}))
    data = pub.read_changing(pub.changing_path(other))
    assert data is not None and data["pending"] == [".plumb/requirements/SR-005.md"]


def test_prompt_delta_once_then_stop_line_for_the_owner(tmp_path: Path,
                                                       hook_input) -> None:  # noqa: ANN001
    main, other = _pair(tmp_path)
    _edit_with_hooks(other, hook_input, "feat-x: pins the stated group")
    line = 'plumb: SR-005 "relay checks" is also being changed on branch feat-x'
    ask = hook_input("UserPromptSubmit", prompt="SR-005 relay checks need a change")
    assert line in _call(prompt, main, ask, backend=None)
    assert line not in _call(prompt, main, ask, backend=None)      # once per session
    # this worktree's stop: the turn touched SR-005, already told this session: not again
    message = _edit_with_hooks(main, hook_input, "main: pins only the affirmed records")
    assert line not in message.get("systemMessage", "")
    # retired: "feat-x's session, whose prompt was about something else, hears it at its
    # stop". SR-012 (INT-008: at the end of a turn only cards; everything else is logged for
    # the owner to read) removed the awareness lines from the owner's end-of-turn text; the
    # overlap stays in the brief, the prompt delta and the status line (SR-078).


def test_stop_keeps_the_branch_claim_in_step(tmp_path: Path, hook_input) -> None:  # noqa: ANN001
    """R17: a record changed by any means (here a plain edit) is claimed at the stop."""
    from plumb.awareness import inflight

    main, other = _pair(tmp_path)
    _edit_with_hooks(other, hook_input, "feat-x: pins the stated group")
    _oid, data = inflight.read(main, allow_git=True)
    [claim] = data["claims"]
    assert claim["branch"] == "feat-x" and set(claim["records"]) == {"SR-005"}
    assert claim["records"]["SR-005"]["text"] == "feat-x: pins the stated group"
