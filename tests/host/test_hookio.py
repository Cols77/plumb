"""H1: hook I/O, the deadline and the catch-all (spec 6, 10)."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from plumb.hosts.claude_code import hookio

pytestmark = pytest.mark.sr("SR-014")


def _run(handler, repo: Path, payload: str, **kwargs) -> tuple[int, str]:
    out = io.StringIO()
    code = hookio.run_hook("test", handler, stdin=io.StringIO(payload), stdout=out, root=repo,
                           **kwargs)
    return code, out.getvalue()


def test_internal_error_exits_zero_with_notice(repo: Path, hook_input) -> None:
    def broken(ctx):
        raise RuntimeError("boom in the hook")

    code, out = _run(broken, repo, hook_input("Stop"), budget_ms=500)
    assert code == 0
    assert out.strip() == hookio.SKIP_ERROR
    log = (repo / ".plumb" / "session" / "errors.log").read_text(encoding="utf-8")
    assert "boom in the hook" in log
    assert "test" in log


def test_internal_error_in_json_hook_is_a_system_message(repo: Path, hook_input) -> None:
    def broken(ctx):
        raise ValueError("bad")

    code, out = _run(broken, repo, hook_input("Stop"), budget_ms=500, json_output=True)
    assert code == 0
    assert json.loads(out) == {"systemMessage": hookio.SKIP_ERROR}


def test_deadline_skips_with_budget_notice(repo: Path, hook_input) -> None:
    def slow(ctx):
        time.sleep(0.05)
        ctx.deadline.check("slow step")
        return hookio.HookOutput(text="never printed")

    code, out = _run(slow, repo, hook_input("UserPromptSubmit"), budget_ms=10)
    assert code == 0
    assert out.strip() == hookio.SKIP_BUDGET


def test_block_output_shape(repo: Path, hook_input) -> None:
    def blocking(ctx):
        return hookio.HookOutput(block_reason="plumb: run the tests")

    code, out = _run(blocking, repo, hook_input("Stop"), budget_ms=500)
    assert code == 0
    assert json.loads(out) == {"decision": "block", "reason": "plumb: run the tests"}


def test_system_message_and_plain_text_outputs(repo: Path, hook_input) -> None:
    code, out = _run(lambda ctx: hookio.HookOutput(system_message="plumb: ok"), repo,
                     hook_input("Stop"), budget_ms=500)
    assert json.loads(out) == {"systemMessage": "plumb: ok"}
    code, out = _run(lambda ctx: hookio.HookOutput(text="line 1\nline 2"), repo,
                     hook_input("SessionStart"), budget_ms=500)
    assert out == "line 1\nline 2\n"
    code, out = _run(lambda ctx: None, repo, hook_input("Stop"), budget_ms=500)
    assert out == ""


def test_handler_gets_input_session_and_root(repo: Path, hook_input) -> None:
    seen = {}

    def handler(ctx):
        seen.update(data=ctx.data, root=ctx.root, session=ctx.session_id)

    _run(handler, repo, hook_input("Stop", session_id="../evil id"), budget_ms=500)
    assert seen["root"] == repo
    assert seen["data"]["hook_event_name"] == "Stop"
    assert "/" not in seen["session"] and ".." not in seen["session"]


def test_unreadable_input_still_exits_zero(repo: Path) -> None:
    code, out = _run(lambda ctx: hookio.HookOutput(text=str(ctx.data)), repo, "not json",
                     budget_ms=500)
    assert code == 0
    assert out.strip() == "{}"


def test_repository_without_plumb_is_left_alone(tmp_path: Path, hook_input,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    called = []
    out = io.StringIO()
    code = hookio.run_hook("test", lambda ctx: called.append(1),
                           stdin=io.StringIO(hook_input("Stop", cwd=str(tmp_path))),
                           stdout=out, budget_ms=500)
    assert code == 0 and not called and out.getvalue() == ""


def test_root_found_from_input_cwd(repo: Path, hook_input,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    sub = repo / "pkg"
    sub.mkdir()
    seen = []
    hookio.run_hook("test", lambda ctx: seen.append(ctx.root),
                    stdin=io.StringIO(hook_input("Stop", cwd=str(sub))), stdout=io.StringIO(),
                    budget_ms=500)
    assert seen == [repo]
