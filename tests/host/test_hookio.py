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


def test_kept_lines_survive_a_budget_cut(repo: Path, hook_input) -> None:
    """The intent-translation lines a handler keeps are printed even when a later step is
    cut by the deadline; only the skipped step is named."""

    def partly_slow(ctx):
        ctx.keep(["plumb: relevant records", "plumb: relay line"])
        time.sleep(0.05)
        ctx.deadline.check("covering tests")
        return hookio.HookOutput(text="never printed")

    code, out = _run(partly_slow, repo, hook_input("UserPromptSubmit"), budget_ms=10)
    assert code == 0
    assert out.splitlines() == ["plumb: relevant records", "plumb: relay line",
                                "plumb: check skipped (budget): covering tests"]


def test_kept_lines_survive_in_a_json_hook(repo: Path, hook_input) -> None:
    def partly_slow(ctx):
        ctx.keep(["plumb: proposed SR-001 read-back"])
        time.sleep(0.05)
        ctx.deadline.check("fidelity")

    code, out = _run(partly_slow, repo, hook_input("Stop"), budget_ms=10, json_output=True)
    assert json.loads(out) == {"systemMessage": "plumb: proposed SR-001 read-back\n"
                                                "plumb: check skipped (budget): fidelity"}


def test_kept_lines_survive_an_internal_error(repo: Path, hook_input) -> None:
    def broken_late(ctx):
        ctx.keep(["plumb: relay line"])
        raise RuntimeError("late failure")

    code, out = _run(broken_late, repo, hook_input("UserPromptSubmit"), budget_ms=500)
    assert out.splitlines() == ["plumb: relay line", hookio.SKIP_ERROR]


def test_watchdog_prints_the_kept_lines(repo: Path, hook_input, tmp_path: Path) -> None:
    """The hard-limit watchdog prints what the handler kept, not a bare notice."""
    import subprocess
    import sys

    script = tmp_path / "wd.py"
    script.write_text(
        "import io, sys, time\n"
        "from plumb.hosts.claude_code import hookio\n"
        "def h(ctx):\n"
        "    ctx.keep(['plumb: relay line'])\n"
        "    time.sleep(5)\n"
        f"hookio.run_hook('t', h, stdin=io.StringIO('{{}}'), stdout=sys.stdout, root=r'{repo}',\n"
        "                 budget_ms=100, watchdog=True, start=time.monotonic() - 28.0)\n",
        encoding="utf-8")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                            timeout=30, check=False)
    assert result.stdout.splitlines() == ["plumb: relay line", hookio.SKIP_BUDGET]


def test_default_budgets_sit_just_under_the_hard_limit(repo: Path) -> None:
    """Soft budgets generous but under the hard limit (SR-181): a loaded 2-core machine must not cut
    the read-back on a routine turn; the watchdog still bounds the hook."""
    from plumb.config import HooksConfig

    budgets = HooksConfig().budget_ms
    for name in ("session_start", "prompt", "stop"):
        assert 1200 <= budgets[name] < hookio.HARD_LIMIT_S * 1000, name
        assert hookio.hook_budget(name)(repo) == budgets[name]


_GRACE_SCRIPT = (
    "import io, sys, time\n"
    "from plumb.hosts.claude_code import hookio\n"
    "def h(ctx):\n"
    "    time.sleep(0.5)\n"  # the hard limit (0.3 s from start) passes before anything is kept
    "    ctx.keep(['plumb: read-back'])\n"
    "    time.sleep(0.3)\n"
    "    return hookio.HookOutput(text='plumb: read-back')\n"
    "hookio.HARD_LIMIT_S = 0.3\n"
    "hookio.run_hook('t', h, stdin=io.StringIO('{{}}'), stdout=sys.stdout, root=r'{repo}',\n"
    "                 budget_ms=100, watchdog=True, start=time.monotonic(), grace_s={grace})\n")


@pytest.mark.parametrize(("grace", "expected"), [
    (1.0, ["plumb: read-back"]),  # nothing kept at the limit: wait for the read-back
    (0.0, [hookio.SKIP_BUDGET]),  # no grace: the bare notice, as before
])
def test_watchdog_grace_waits_for_the_first_kept_line(repo: Path, tmp_path: Path, grace: float,
                                                      expected: list[str]) -> None:
    """R1: a hook cut before it kept anything has nothing to say; a hook with a grace lets the
    read-back through if it arrives within the grace."""
    import subprocess
    import sys

    script = tmp_path / "grace.py"
    script.write_text(_GRACE_SCRIPT.format(repo=repo, grace=grace), encoding="utf-8")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                            timeout=30, check=False)
    assert result.stdout.splitlines() == expected
