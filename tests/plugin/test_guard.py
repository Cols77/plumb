"""The guard (SP7 4.3 re-aligned with SP8, slice 6; SR-112, SR-086 EX-3): one table denies what
only the owner does, in every launcher spelling, from the plugin's pre-tool hook; the legacy deny
rules and the mod's table come from the same table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import guard
from plumb.hosts.claude_code import pretool

from .helpers import (
    PLUGIN,
    adopted_repo,
    env_with,
    hook_data,
    needs_sh,
    ready_home,
    real_python,
    run_hook,
    sentinel_bin,
)

pytestmark = [pytest.mark.sr("SR-209")]

LAUNCHERS = (
    "plumb",
    "plumb.exe",
    "plumb.cmd",
    "uv run plumb",
    "uv run --no-sync plumb",
    "python -m plumb",
    "python3 -m plumb",
    "C:/work/app/.venv/Scripts/python.exe -m plumb",
    "/home/me/app/.venv/bin/python -m plumb",
    '"C:/Program Files/Python312/python.exe" -m plumb',
    "/home/me/.claude/plugins/plumb/bin/plumb",
    "C:/Users/me/.plumb/bin/plumb",
)

DENIED = (
    "approve SR-001",
    "approve --proposed",
    "revoke SR-001",
    "tests waive --reason flaky",
    "triage --approve",
    "triage --group parsing --approve",
    "spec approve FEAT-001",
    "config auto-approve on",
    "config show",
    "turn start --prompt-file p.txt",
    "hook prompt",
    "hook question-answer",
    "conflict choose INT-004 --take ours",
    "owner confirm SR-001",
    "mod hello --session s1 --json",
    "mod press --session s1 --offer abc --choice 1",
    "mod typed --session s1",
)

ALLOWED = (
    "status",
    "status --card",
    "show SR-001",
    "explain the reminders",
    "conflict choose INT-004 --take ours --prompt 9f2c --quote ours",
    "conflict relay INT-004 --prompt 9f2c --quote ours",
    "owner confirm SR-001 --prompt 9f2c",
    "mod snapshot --session s1 --json",
    "config card compact",
    "capture --file read-back.yaml",
)


@pytest.mark.parametrize("launcher", LAUNCHERS)
@pytest.mark.parametrize("form", DENIED)
def test_denied(launcher: str, form: str) -> None:
    reason = guard.denied("Bash", {"command": f"{launcher} {form}"})
    assert reason and reason.startswith("plumb: refused:")


@pytest.mark.parametrize("launcher", LAUNCHERS)
@pytest.mark.parametrize("form", ALLOWED)
def test_allowed(launcher: str, form: str) -> None:
    assert guard.denied("Bash", {"command": f"{launcher} {form}"}) is None


@pytest.mark.parametrize("command", [
    "cd app && plumb approve SR-001",
    "plumb status; plumb approve SR-001",
    "true || plumb revoke SR-001",
    "plumb status | plumb mod press --offer x",
    "echo $(plumb approve SR-001)",
    'echo "$(plumb revoke SR-001)"',
    "echo `plumb approve SR-001`",
    'bash -c "plumb approve SR-001"',
    "sh -lc 'plumb approve SR-001'",
    'powershell -Command "plumb approve SR-001"',
    'eval "plumb approve SR-001"',
    "env FOO=1 plumb approve SR-001",
    "PYTHONPATH=src python -m plumb approve SR-001",
    "exec plumb approve SR-001",
    "(plumb approve SR-001)",
    "plumb status\nplumb approve SR-001",
])
def test_denied_inside_compound_commands(command: str) -> None:
    assert guard.denied("Bash", {"command": command})


@pytest.mark.parametrize("command", [
    'git commit -m "plumb approve SR-001 is the owner\'s alone"',
    "git commit -F - <<'EOF'\nGuard plumb approve and plumb revoke\n\nSR: SR-112\nEOF",
    "grep -rn 'plumb approve' src",
    "echo plumb approve",
    "plumb explain approve",
])
def test_words_about_plumb_are_not_commands(command: str) -> None:
    assert guard.denied("Bash", {"command": command}) is None


def test_marker_named_anywhere() -> None:
    for command in ("unset PLUMB_AGENT_SESSION", "env -u PLUMB_AGENT_SESSION plumb approve",
                    "echo $PLUMB_AGENT_SESSION"):
        assert guard.denied("Bash", {"command": command}) == guard.MARKER_REASON


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit", "NotebookEdit"])
def test_edits_under_the_log(tool: str) -> None:
    for path in (".plumb/log/events/2026/x.json", "C:\\r\\.plumb\\log\\prompts.jsonl",
                 "/home/me/r/.plumb/log/approval/a.json"):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        assert guard.denied(tool, {key: path}) == guard.LOG_REASON
    assert guard.denied(tool, {"file_path": ".plumb/requirements/SR-001.md"}) is None
    assert guard.denied(tool, {"file_path": "src/log/x.py"}) is None


def test_pre_tool_hook_answers_deny(tmp_path: Path) -> None:
    """The Python hook (the plugin's pre-tool) answers Claude Code's deny with the reason."""
    import io

    out = io.StringIO()
    data = {"session_id": "s1", "tool_name": "Bash",
            "tool_input": {"command": "plumb approve SR-001"}}
    assert pretool.main(root=tmp_path, stdin=io.StringIO(json.dumps(data)), stdout=out) == 0
    answer = json.loads(out.getvalue())["hookSpecificOutput"]
    assert answer["permissionDecision"] == "deny"
    assert "approve" in answer["permissionDecisionReason"]
    out = io.StringIO()
    data["tool_input"] = {"command": "plumb status"}
    pretool.main(root=tmp_path, stdin=io.StringIO(json.dumps(data)), stdout=out)
    assert out.getvalue() == ""


@needs_sh
def test_plugin_hook_denies_through_sh(tmp_path: Path) -> None:
    """End to end: Claude Code runs the plugin's pre-tool hook, which runs the guard in plumb's
    own environment."""
    root = adopted_repo(tmp_path / "repo")
    home = ready_home(tmp_path / "home", real_python(tmp_path / "env" / "python"))
    env = env_with([], PLUMB_HOME=str(home), CLAUDE_PROJECT_DIR=str(root))
    result = run_hook("pre-tool", root, hook_data(
        "pre-tool", tool_input={"command": "uv run plumb mod press --offer x"}), env)
    answer = json.loads(result.stdout)["hookSpecificOutput"]
    assert answer["permissionDecision"] == "deny"
    result = run_hook("pre-tool", root, hook_data("pre-tool"), env)  # plumb status
    assert (result.returncode, result.stdout) == (0, "")


@needs_sh
def test_gate_in_shell_without_python(tmp_path: Path) -> None:
    """SP8's gate stays the fast path: a closed gate refuses an edit in the shell alone."""
    sentinel = tmp_path / "sentinel.txt"
    root = adopted_repo(tmp_path / "repo")
    gate = root / ".plumb" / "session" / "s1" / "gate"
    gate.parent.mkdir(parents=True)
    gate.write_text('{"state": "closed", "reason": "the reminders"}', encoding="utf-8")
    poison = sentinel_bin(tmp_path / "poison", sentinel)
    home = ready_home(tmp_path / "home", poison / "python")
    env = env_with([poison], PLUMB_HOME=str(home), CLAUDE_PROJECT_DIR=str(root))
    result = run_hook("pre-tool", root, hook_data(
        "pre-tool", tool_name="Write", tool_input={"file_path": "src/app.py"}), env)
    answer = json.loads(result.stdout)["hookSpecificOutput"]
    assert answer["permissionDecision"] == "deny"
    assert "the reminders" in answer["permissionDecisionReason"]
    assert not sentinel.exists()
    # an edit that names nothing of plumb's, with the gate open: no Python either
    gate.write_text('{"state": "open"}', encoding="utf-8")
    result = run_hook("pre-tool", root, hook_data(
        "pre-tool", tool_name="Write", tool_input={"file_path": "src/app.py"}), env)
    assert (result.returncode, result.stdout) == (0, "")
    assert not sentinel.exists()


def test_install_rules_from_same_table() -> None:
    from plumb.hosts.claude_code.install import (
        STANDARD_PREFIXES,
        Launcher,
        deny_rules,
        is_plumb_deny,
    )

    rules = deny_rules(Launcher("path", "plumb", "plumb"))
    forms = guard.legacy_forms()
    for row in guard.TABLE:
        if row.legacy:
            assert any(f.startswith(" ".join(row.words)) for f in forms)
    for form in forms:
        for prefix in STANDARD_PREFIXES:
            assert f"Bash({prefix} {form}:*)" in rules
            # what the rule denies, the guard denies too
            assert guard.denied("Bash", {"command": f"{prefix} {form} x"}), form
    assert all(is_plumb_deny(rule) for rule in rules)


def test_mod_table_is_generated_from_the_table() -> None:
    text = (PLUGIN / "hooks" / "guard.gen.ts").read_text(encoding="utf-8")
    start = text.index("GUARD_TABLE: GuardRow[] = ") + len("GUARD_TABLE: GuardRow[] = ")
    assert json.loads(text[start:].rstrip().rstrip(";")) == guard.table_data()
