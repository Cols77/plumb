"""SR-414: the owner asks to see a loop in its own window. A live loop's window is brought to the
front (nothing new opens); when the platform cannot, plumb says so and names the session and its
folder; an idle loop still opens a new session (SR-394). No test raises a real window: the
seam ``loops.raise_window(title, *, which, run, platform, env) -> bool`` is faked or given fake
programs.

SR-305: the loops listing carries each intent loop's steps (gate, findings left) and tasks."""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path
from typing import Any

import pytest
from mod.helpers import DIGEST, KEY, run_mod

from plumb.understand import loops

from understand.test_loops import _loop, _passed
from understand.test_loops_reopen import ID, Windows, window  # noqa: F401  (the window fixture)

LIVE = {"busy": {"status": "busy", "cwd": "/somewhere/else"}}


@pytest.fixture
def live(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = _loop(repo, "busy", "sha256:" + "a" * 64)
    monkeypatch.setattr(loops, "claude_sessions", lambda: LIVE)
    return path


def _mod_reopen(repo: Path, monkeypatch: Any, capsys: Any) -> tuple[int, Any]:
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, repo, "reopen", "--loop", ID, stdin={"key": KEY})
    return code, answer


@pytest.mark.sr("SR-414")
def test_ex1_a_live_loop_s_window_is_raised_and_nothing_new_opens(
        repo: Path, live: Path, window: Windows, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    titles: list[str] = []
    monkeypatch.setattr(loops, "raise_window", lambda title, **kw: titles.append(title) or True,
                        raising=False)
    code, answer = _mod_reopen(repo, monkeypatch, capsys)
    assert code == 0 and answer["shown"] is True and answer["opened"] is False
    assert titles and titles[0].startswith("plumb: ")      # the name SR-394 gave the window
    assert window.calls == []


@pytest.mark.sr("SR-414")
def test_ex2_no_way_to_raise_a_window_says_so_and_names_the_session_and_folder(
        repo: Path, live: Path, window: Windows, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(loops, "raise_window", lambda title, **kw: False, raising=False)
    code, answer = _mod_reopen(repo, monkeypatch, capsys)
    assert code == 1 and answer["shown"] is False and answer["opened"] is False
    assert "cannot bring" in answer["line"] and "busy" in answer["line"]
    assert repo.as_posix() in answer["line"]
    assert window.calls == []


@pytest.mark.sr("SR-414")
def test_ex3_an_idle_loop_still_opens_a_new_session(
        repo: Path, window: Windows, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    _loop(repo, "gone", "sha256:" + "a" * 64)
    monkeypatch.setattr(loops, "claude_sessions", lambda: {})
    monkeypatch.setattr(loops, "raise_window", lambda title, **kw: pytest.fail("raised"),
                        raising=False)
    code, answer = _mod_reopen(repo, monkeypatch, capsys)
    assert code == 0 and answer["opened"] is True and len(window.calls) == 1


@pytest.mark.sr("SR-414")
@pytest.mark.parametrize("platform,program,seen", [("linux", "xdotool", "plumb: x loop"),
                                                    ("darwin", "osascript", "plumb: x loop"),
                                                    ("win32", None, "plumb: x loop")])
def test_raise_window_asks_the_platform_s_program_by_the_window_title(
        platform: str, program: str | None, seen: str) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kw: Any) -> Any:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="12345\n", stderr="")

    ok = loops.raise_window("plumb: x loop", which=lambda p: f"/usr/bin/{p}", run=run,
                            platform=platform, env={"DISPLAY": ":0"})
    assert ok is True and calls
    assert any(seen in " ".join(c) for c in calls)
    if program:
        assert calls[0][0].endswith(program) or calls[0][0] in (program, "wmctrl")


@pytest.mark.sr("SR-414")
def test_raise_window_is_false_without_a_program_or_a_display() -> None:
    nothing = functools.partial(loops.raise_window, "plumb: x", which=lambda p: None,
                                run=lambda *a, **k: pytest.fail("ran"), platform="linux",
                                env={"DISPLAY": ":0"})
    assert nothing() is False
    assert loops.raise_window("plumb: x", which=lambda p: "/usr/bin/xdotool", platform="linux",
                              run=lambda *a, **k: pytest.fail("ran"), env={}) is False


@pytest.mark.sr("SR-305")
def test_the_listing_carries_each_step_s_gate_findings_and_the_tasks(repo: Path) -> None:
    stages = {"clarify": {"state": "passed", "at": "t", "findings": 2, "left": ["a", "b"]},
              "plan": {"state": "passed", "at": "t", "findings": 2, "left": ["c", "d"]}}
    _loop(repo, "busy", "sha256:" + "a" * 64, stages=stages,
          tasks={"label": "building", "done": 3, "total": 4, "left": ["the colours slice"]})
    row = loops.listing(repo, agents=LIVE)["rows"][0]
    steps = {s["name"]: s for s in row["steps"]}
    assert list(steps) == ["clarify", "plan", "build", "proven"]
    assert (steps["clarify"]["gate"], steps["clarify"]["findings"], steps["clarify"]["left"]) == ("passed", 2, ["a", "b"])
    assert (steps["plan"]["gate"], steps["plan"]["findings"]) == ("passed", 2)
    assert steps["build"]["gate"] == "open" and steps["build"]["mark"] == "current"
    assert steps["proven"]["gate"] == "to come" and steps["proven"]["mark"] == "todo"
    assert row["tasks"] == {"done": 3, "total": 4, "left": ["the colours slice"]}


@pytest.mark.sr("SR-305")
def test_a_refused_gate_reads_refused_on_the_current_step(repo: Path) -> None:
    _loop(repo, "busy", "sha256:" + "a" * 64, stopped="clarify gate: 2 finding(s) to fix")
    steps = {s["name"]: s for s in loops.listing(repo, agents=LIVE)["rows"][0]["steps"]}
    assert steps["clarify"]["gate"] == "refused" and steps["clarify"]["mark"] == "stopped"
    assert steps["plan"]["gate"] == "to come"
