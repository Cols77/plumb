"""SHOW S4: the check before an edit (SR-103 EX-5)."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from plumb.hosts.claude_code import install, pretool
from plumb.understand import gate

pytestmark = pytest.mark.sr("SR-223")

SESSION = "7f3a9c52-1d4e-4b6a-9a10-2c5d8e0f1b34"
SCRIPT = Path(install.__file__).parent / "templates" / "gate.sh"
SH = shutil.which("sh")


def _closed(repo: Path, session: str = SESSION, reason: str = "your request is being checked"
            ) -> None:
    gate.close(repo, session, "sha256:" + "ab" * 32, reason)


def _hook_input(tool: str, session: str = SESSION) -> str:
    return json.dumps({"session_id": session, "transcript_path": "", "cwd": ".",
                       "hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": {"file_path": "src/a.py", "content": "x"}})


def _script(repo: Path, tool: str, session: str = SESSION) -> tuple[str, int]:
    done = subprocess.run([SH or "sh", str(SCRIPT)], input=_hook_input(tool, session),
                          capture_output=True, text=True, encoding="utf-8",
                          env={"PATH": __import__("os").environ["PATH"],
                               "CLAUDE_PROJECT_DIR": str(repo)}, timeout=20)
    return done.stdout, done.returncode


def test_ex5_edit_refused_while_closed_message_names_clarify_wait(repo: Path) -> None:
    _closed(repo)
    for tool in pretool.EDIT_TOOLS:
        answer = pretool.decide(repo, SESSION, tool)
        out = answer["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny" and out["hookEventName"] == "PreToolUse"
        assert "plumb clarify --wait" in out["permissionDecisionReason"]
        assert "your request is being checked" in out["permissionDecisionReason"]
    # the Python route of the hook prints the same answer
    stdout = io.StringIO()
    assert pretool.main(root=repo, stdin=io.StringIO(_hook_input("Edit")), stdout=stdout) == 0
    assert json.loads(stdout.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_gate_sh_lets_the_card_diagram_through_while_closed(repo: Path) -> None:
    """SR-146: the agent draws the diagram a card names while the card is open."""
    _closed(repo)
    run = lambda path: subprocess.run(  # noqa: E731
        [SH or "sh", str(SCRIPT)], capture_output=True, text=True, timeout=20,
        input=json.dumps({"session_id": SESSION, "tool_name": "Write",
                          "tool_input": {"file_path": path}}),
        env={"PATH": __import__("os").environ["PATH"], "CLAUDE_PROJECT_DIR": str(repo)}).stdout
    assert run(f"{repo}/.plumb/session/{SESSION}/diagrams/ab12.html") == ""
    assert run(rf"C:\x\.plumb\session\{SESSION}\diagrams\ab12.html") == ""
    assert "deny" in run(f"{repo}/.plumb/session/{SESSION}/diagrams/../../../src/a.py")
    assert "deny" in run("src/a.py")


def test_python_route_lets_the_card_diagram_through_while_closed(repo: Path) -> None:
    """SR-146: the hook falls through to this route for any path naming .plumb."""
    _closed(repo)
    ok = {"file_path": rf"C:\x\.plumb\session\{SESSION}\diagrams\ab12.html"}
    assert pretool.decide(repo, SESSION, "Write", ok) == {}
    bad = {"file_path": f"{repo}/.plumb/session/{SESSION}/diagrams/../../../src/a.py"}
    assert pretool.decide(repo, SESSION, "Write", bad)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_edit_allowed_when_open(repo: Path) -> None:
    assert pretool.decide(repo, SESSION, "Edit") == {}            # no gate file at all
    _closed(repo)
    gate.open(_core(repo), SESSION, "sha256:" + "ab" * 32, "clarify", "nothing is unclear")
    assert pretool.decide(repo, SESSION, "Edit") == {}
    stdout = io.StringIO()
    pretool.main(root=repo, stdin=io.StringIO(_hook_input("Write")), stdout=stdout)
    assert stdout.getvalue() == ""


def _core(repo: Path):
    from plumb.api import open_core

    return open_core(repo)


def test_another_session_is_not_held(repo: Path) -> None:
    _closed(repo)
    assert pretool.decide(repo, "someone-else", "Edit") == {}


def test_script_text_contains_no_python() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    for word in ("python", "plumb -m", "uv run", "import ", "json.loads"):
        assert word not in text.lower().replace("plumb clarify --wait", "")
    assert "sed" not in text.split()                  # nor any other program: builtins only
    for tool in pretool.EDIT_TOOLS:
        assert tool in text
    assert "plumb clarify --wait" in text and "shell are not checked" in text
    assert pretool.REASON.split("{reason}")[1].strip(". ") in text.replace("\n", " ")


@pytest.mark.skipif(SH is None, reason="no POSIX shell to run the script")
def test_script_refuses_and_allows_like_the_python_route(repo: Path) -> None:
    out, code = _script(repo, "Edit")
    assert (out, code) == ("", 0)                                  # no gate file: allowed
    _closed(repo)
    out, code = _script(repo, "Edit")
    assert code == 0
    sent = json.loads(out)["hookSpecificOutput"]
    assert sent == pretool.decide(repo, SESSION, "Edit")["hookSpecificOutput"]
    assert _script(repo, "Read") == ("", 0)
    assert _script(repo, "Bash") == ("", 0)
    assert _script(repo, "Edit", session="not/a safe id") == ("", 0)
    gate.open(_core(repo), SESSION, "sha256:" + "ab" * 32, "clarify", "nothing is unclear")
    assert _script(repo, "Write") == ("", 0)


@pytest.mark.skipif(SH is None, reason="no POSIX shell to run the script")
def test_script_answers_inside_50_ms_min_of_5(repo: Path) -> None:
    _closed(repo)
    payload = _hook_input("Edit")
    env = {"PATH": __import__("os").environ["PATH"], "CLAUDE_PROJECT_DIR": str(repo)}
    # the shell's own start-up is measured apart: the budget is for what the script adds
    base = []
    mine = []
    for _ in range(5):
        t0 = time.perf_counter()
        subprocess.run([SH, "-c", "exit 0"], input=payload, capture_output=True, text=True,
                       env=env)
        base.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        done = subprocess.run([SH, str(SCRIPT)], input=payload, capture_output=True,
                              text=True, env=env)
        mine.append(time.perf_counter() - t0)
        assert "deny" in done.stdout
    added = min(mine) - min(base)
    assert added < 0.050 * 0.9, f"the script adds {added * 1000:.0f} ms"


def test_bash_edit_not_gated_and_reason_says_so(repo: Path) -> None:
    _closed(repo)
    assert pretool.decide(repo, SESSION, "Bash") == {}
    reason = pretool.decide(repo, SESSION, "Edit")["hookSpecificOutput"][
        "permissionDecisionReason"]
    assert "edits made through the shell are not checked" in reason


def test_install_registers_pretool(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "plumb.claims", None)
    uv = install.Launcher("uv", "uv run --no-sync plumb", "uv run --no-sync plumb")
    assert "pre-tool" in install.available_hooks()
    install.install(repo, launcher=uv, hooks=("session-start", "pre-tool"))
    settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    (group,) = settings["hooks"]["PreToolUse"]
    assert group["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
    (hook,) = group["hooks"]
    assert hook["command"] == 'sh "$CLAUDE_PROJECT_DIR/.claude/plumb/gate.sh"'
    assert "async" not in hook
    script = repo / ".claude" / "plumb" / "gate.sh"
    assert script.read_text(encoding="utf-8") == SCRIPT.read_text(encoding="utf-8")
    assert b"\r\n" not in script.read_bytes()
    status = "\n".join(install.status(repo))
    assert "pre-tool" in status.split("not installed:")[0]
    # idempotent, and uninstall takes the entry and the script away again
    again = install.install(repo, launcher=uv, hooks=("session-start", "pre-tool"))
    assert not again.changed
    install.uninstall(repo)
    assert not script.exists()
    left = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8")) \
        if (repo / ".claude" / "settings.json").exists() else {}
    assert "PreToolUse" not in left.get("hooks", {})


def test_the_hook_route_is_listed_in_the_help(capsys: pytest.CaptureFixture) -> None:
    from plumb.hosts.claude_code import cli

    assert cli.run("hook", ["--help"]) == 0
    assert "pre-tool" in capsys.readouterr().out


@pytest.mark.sr("SR-226")
def test_python_route_walks_up_from_a_subfolder(repo: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-121: a session started in src/ reads the gate of the .plumb/ above it, as gate.sh
    does, instead of a src/.plumb that does not exist."""
    _closed(repo)
    src = repo / "src"
    src.mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(src))
    monkeypatch.chdir(src)
    stdout = io.StringIO()
    assert pretool.main(stdin=io.StringIO(_hook_input("Edit")), stdout=stdout) == 0
    assert json.loads(stdout.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"
