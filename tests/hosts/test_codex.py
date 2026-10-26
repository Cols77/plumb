"""The Codex adapter (sp4 4.1, SR-054)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from hosts_helpers import (
    approvals_written,
    approve_in_agent_shell,
    make_project,
    snapshot,
)

from plumb.cli import main
from plumb.hosts.codex import install as codex
from plumb.hosts.common import IS_WINDOWS, NO_MARKER_LINE, InstallError, shell_command

pytestmark = pytest.mark.sr("SR-283")

FOREIGN_HOOK = {"type": "command", "command": "echo mine"}
FOREIGN_TOML = '[mcp_servers.other]\ncommand = "other"\n'


@pytest.fixture
def project(repo: Path, write_record, tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))  # no user notify
    make_project(repo, write_record, decision=False)
    (repo / "AGENTS.md").write_text("# Owner's notes\n\nKeep it simple.\n", "utf-8")
    (repo / ".codex").mkdir()
    (repo / ".codex" / "hooks.json").write_text(json.dumps(
        {"hooks": {"Stop": [{"hooks": [FOREIGN_HOOK]}]}}), "utf-8")
    (repo / ".codex" / "config.toml").write_text(FOREIGN_TOML, "utf-8")
    return repo


def _config(root: Path) -> dict:
    return tomllib.loads((root / ".codex" / "config.toml").read_text("utf-8"))


def test_install_idempotent_preserves_foreign(project: Path) -> None:
    codex.install(project)
    first = snapshot(project)
    assert codex.install(project).changed == []
    assert snapshot(project) == first
    agents = (project / "AGENTS.md").read_text("utf-8")
    assert agents.startswith("# Owner's notes\n\nKeep it simple.\n")
    assert agents.count("<!-- plumb:begin -->") == 1 and "turn start" in agents
    hooks = json.loads((project / ".codex" / "hooks.json").read_text("utf-8"))["hooks"]
    assert FOREIGN_HOOK in hooks["Stop"][0]["hooks"]
    for event in ("SessionStart", "UserPromptSubmit", "Stop"):
        commands = [h["command"] for g in hooks[event] for h in g["hooks"]]
        ours = [c for c in commands if "--host codex" in c]
        assert len(ours) == 1 and "--format claude" in ours[0]
    config = _config(project)
    assert config["mcp_servers"]["other"]["command"] == "other"
    assert config["shell_environment_policy"]["set"]["PLUMB_AGENT_SESSION"] == "codex"
    assert config["notify"][-1] == "--notify" and "codex" in config["notify"]


def test_uninstall_removes_only_plumb(project: Path) -> None:
    before = snapshot(project)
    codex.install(project)
    codex.uninstall(project)
    after = snapshot(project)
    assert after[".codex/config.toml"] == before[".codex/config.toml"]
    assert json.loads(after[".codex/hooks.json"]) == json.loads(before[".codex/hooks.json"])
    assert after["AGENTS.md"] == before["AGENTS.md"]


def test_dry_run_writes_nothing(project: Path, monkeypatch, capsys) -> None:
    before = snapshot(project)
    monkeypatch.chdir(project)
    assert main(["hosts", "install", "codex", "--dry-run"]) == 0
    assert "would change" in capsys.readouterr().out
    assert snapshot(project) == before


def test_owner_only_refused_in_agent_shell(project: Path, monkeypatch, capsys) -> None:
    codex.install(project)
    marker = _config(project)["shell_environment_policy"]["set"]
    assert approve_in_agent_shell(project, monkeypatch, marker) == 3
    assert approve_in_agent_shell(project, monkeypatch, {}) == 3  # no marker: no terminal
    assert approvals_written(project) == []


def test_status_names_missing_marker(project: Path, monkeypatch, capsys) -> None:
    (project / ".codex" / "config.toml").write_text(
        FOREIGN_TOML + '[shell_environment_policy]\ninherit = "core"\n', "utf-8")
    report = codex.install(project)
    assert any("session marker not set" in line for line in report.lines)
    assert "PLUMB_AGENT_SESSION" not in (project / ".codex" / "config.toml").read_text("utf-8")
    monkeypatch.chdir(project)
    assert main(["hosts", "status", "codex"]) == 0
    out = capsys.readouterr().out
    assert NO_MARKER_LINE in out and "tamper-evident" in out
    assert "UserPromptSubmit" in out


def test_user_notify_kept(project: Path, tmp_path: Path) -> None:
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text('notify = ["mine"]\n', "utf-8")
    report = codex.install(project)
    assert "notify" not in _config(project)
    assert any("notify kept" in line for line in report.lines)


def _link_running_venv(project: Path) -> None:
    """``project/.venv`` names the venv running the tests (a junction on Windows)."""
    target = project / ".venv"
    if IS_WINDOWS:
        import _winapi

        _winapi.CreateJunction(sys.prefix, str(target))
    else:
        target.symlink_to(sys.prefix, target_is_directory=True)


def _platform_shells(command: str) -> list[list[str] | str]:
    if IS_WINDOWS:  # Codex runs hook commands through cmd or PowerShell
        return [f'cmd /d /s /c "{command}"',
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]]
    return [["sh", "-c", command]]


def test_hook_commands_run_in_the_platform_shell(project: Path) -> None:
    """Every hook command written to .codex/hooks.json runs as written in the platform shell
    (cmd and PowerShell on Windows), with the project's venv interpreter as the launcher."""
    _link_running_venv(project)
    codex.install(project, launcher="venv")
    hooks = json.loads((project / ".codex" / "hooks.json").read_text("utf-8"))["hooks"]
    ours = {name: next(h["command"] for g in hooks[name] for h in g["hooks"]
                       if "--host codex" in h["command"])
            for name, _ in codex.EVENTS}
    start = ours["SessionStart"]
    for name, event in codex.EVENTS:  # one renderer: the commands differ by event only
        assert ours[name] == start.replace(" session-start ", f" {event} ")
    assert "'" not in start
    env = {k: v for k, v in os.environ.items() if k != "PLUMB_AGENT_SESSION"}
    for shell in _platform_shells(start):
        result = subprocess.run(shell, cwd=project, input="{}", capture_output=True,
                                text=True, encoding="utf-8", env=env, timeout=120)
        assert result.returncode == 0, (shell, result.stdout, result.stderr)
        # SR-374: an empty project has nothing to say at session start (no counts)
        assert not result.stdout.strip() or "hookSpecificOutput" in result.stdout, (
            shell, result.stdout, result.stderr)
        assert not (project / ".plumb" / "session" / "errors.log").exists()


def test_windows_hook_command_refuses_what_cmd_and_powershell_cannot_both_run() -> None:
    assert shell_command([".venv/Scripts/python.exe", "-m", "plumb"], windows=True) == \
        ".venv\\Scripts\\python.exe -m plumb"
    with pytest.raises(InstallError, match="cmd and PowerShell"):
        shell_command(["C:/Program Files/py/python.exe", "-m", "plumb"], windows=True)
