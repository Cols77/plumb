"""H5, HS1, HS2: the Claude Code installer (spec 6.7, 5.6 guard layers 1 and 2)."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from plumb.hosts.claude_code import install

pytestmark = pytest.mark.sr("SR-279")

ALL_HOOKS = ("session-start", "prompt", "post-edit", "stop")
UV = install.Launcher("uv", "uv run --no-sync plumb", "uv run --no-sync plumb")


def _settings(repo: Path) -> dict:
    return json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _commands(settings: dict, event: str) -> list[str]:
    return [h["command"] for group in settings.get("hooks", {}).get(event, [])
            for h in group.get("hooks", [])]


@pytest.fixture
def no_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide BRIDGE's plumb.claims so the installer degrades with a notice."""
    monkeypatch.setitem(sys.modules, "plumb.claims", None)


def _install(repo: Path, **kwargs) -> install.InstallReport:
    kwargs.setdefault("launcher", UV)
    kwargs.setdefault("hooks", ALL_HOOKS)
    return install.install(repo, **kwargs)


@pytest.mark.sr("SR-208")
def test_install_writes_hooks_statusline_env_and_deny_rules(repo: Path, no_claims) -> None:
    _install(repo)
    settings = _settings(repo)
    assert _commands(settings, "SessionStart") == ["uv run --no-sync plumb hook session-start"]
    assert _commands(settings, "UserPromptSubmit") == ["uv run --no-sync plumb hook prompt"]
    assert _commands(settings, "PostToolUse") == ["uv run --no-sync plumb hook post-edit"]
    assert settings["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
    assert _commands(settings, "Stop") == ["uv run --no-sync plumb hook stop"]
    assert settings["statusLine"] == {"type": "command",
                                      "command": "uv run --no-sync plumb statusline"}
    assert settings["env"]["PLUMB_AGENT_SESSION"] == "claude-code"
    deny = settings["permissions"]["deny"]
    for rule in ("Bash(plumb approve:*)", "Bash(plumb revoke:*)", "Bash(plumb tests waive:*)",
                 "Bash(uv run plumb approve:*)", "Bash(python -m plumb approve:*)",
                 "Bash(uv run --no-sync plumb approve:*)", "Bash(*PLUMB_AGENT_SESSION*)",
                 "Edit(.plumb/log/**)", "Write(.plumb/log/**)", "MultiEdit(.plumb/log/**)"):
        assert rule in deny
    assert not any("relay" in rule for rule in deny)


def test_install_registers_only_available_hooks(repo: Path, no_claims) -> None:
    _install(repo, hooks=("session-start", "post-edit"))
    settings = _settings(repo)
    assert set(settings["hooks"]) == {"SessionStart", "PostToolUse"}
    _install(repo, hooks=ALL_HOOKS)
    assert set(_settings(repo)["hooks"]) == {"SessionStart", "UserPromptSubmit", "PostToolUse",
                                             "Stop"}


def test_available_hooks_reflects_built_modules() -> None:
    built = install.available_hooks()
    assert "session-start" in built and "post-edit" in built


def test_install_preserves_foreign_settings_and_is_idempotent(repo: Path, no_claims) -> None:
    claude = repo / ".claude"
    claude.mkdir()
    foreign = {
        "model": "opus",
        "env": {"FOO": "1"},
        "permissions": {"allow": ["Bash(git status)"], "deny": ["Bash(rm -rf:*)"]},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo bye"}]}],
                  "PostToolUse": [{"matcher": "Bash", "hooks": [
                      {"type": "command", "command": "lint.sh"}]}]},
        "statusLine": {"type": "command", "command": "my-status"},
    }
    (claude / "settings.json").write_text(json.dumps(foreign), encoding="utf-8")
    _install(repo)
    first = (claude / "settings.json").read_bytes()
    report = _install(repo)
    assert (claude / "settings.json").read_bytes() == first
    assert not report.changed
    settings = _settings(repo)
    assert settings["model"] == "opus" and settings["env"]["FOO"] == "1"
    assert "Bash(git status)" in settings["permissions"]["allow"]
    assert "Bash(rm -rf:*)" in settings["permissions"]["deny"]
    assert _commands(settings, "Stop") == ["echo bye", "uv run --no-sync plumb hook stop"]
    assert "lint.sh" in _commands(settings, "PostToolUse")
    assert settings["statusLine"]["command"] == "my-status"  # a foreign status line is kept
    assert any("status line" in line and "kept" in line for line in report.lines)
    deny = settings["permissions"]["deny"]
    assert len(deny) == len(set(deny))
    assert b"\r\n" not in first


def test_reinstall_with_new_launcher_replaces_plumb_entries(repo: Path, no_claims) -> None:
    _install(repo)
    venv = install.Launcher("venv", '"$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" -m plumb',
                            ".venv/Scripts/python.exe -m plumb")
    _install(repo, launcher=venv)
    settings = _settings(repo)
    assert _commands(settings, "Stop") == [
        '"$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" -m plumb hook stop']
    assert "Bash(.venv/Scripts/python.exe -m plumb approve:*)" in settings["permissions"]["deny"]


def test_post_edit_registered_async(repo: Path, no_claims) -> None:
    _install(repo)
    hook = _settings(repo)["hooks"]["PostToolUse"][0]["hooks"][0]
    assert hook["async"] is True
    stop = _settings(repo)["hooks"]["Stop"][0]["hooks"][0]
    assert "async" not in stop


def test_skill_about_20_lines_names_test_map(repo: Path, no_claims) -> None:
    _install(repo)
    skill = (repo / ".claude" / "skills" / "plumb-records" / "SKILL.md").read_text(
        encoding="utf-8")
    assert skill.startswith("---\nname: plumb-records\n")  # SR-120: /plumb is the command
    body = skill.split("---", 2)[2].strip().splitlines()
    assert 12 <= len(body) <= 40  # the context and the four question rules (SR-248)
    assert ".plumb/test_map.txt" in skill
    assert "uv run --no-sync plumb tests run --changed" in skill
    assert "never" in skill.lower() and "plumb approve" in skill
    assert "{plumb}" not in skill


def test_claude_md_block_idempotent(repo: Path, no_claims) -> None:
    (repo / "CLAUDE.md").write_text("# Project\n\nOwn notes.\n", encoding="utf-8")
    _install(repo)
    _install(repo)
    text = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# Project\n\nOwn notes.\n")
    assert text.count("<!-- plumb:begin -->") == 1 and text.count("<!-- plumb:end -->") == 1
    assert ".plumb/test_map.txt" in text and "brief" in text


def test_install_calls_commit_msg_installer_or_notes_missing(repo: Path,
                                                            monkeypatch: pytest.MonkeyPatch
                                                            ) -> None:
    monkeypatch.setitem(sys.modules, "plumb.claims", None)
    report = _install(repo)
    assert any("commit-msg" in line and "not available" in line for line in report.lines)

    calls = []
    fake = types.ModuleType("plumb.claims")

    def install_commit_msg_hook(root: Path, interpreter: str) -> Path:
        calls.append((root, interpreter))
        return root / ".git" / "hooks" / "commit-msg"

    fake.install_commit_msg_hook = install_commit_msg_hook
    monkeypatch.setitem(sys.modules, "plumb.claims", fake)
    report = _install(repo)
    assert calls == [(repo, sys.executable)]
    assert any("commit-msg" in line and "installed" in line for line in report.lines)


def test_commit_msg_installer_failure_is_reported(repo: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("plumb.claims")

    def install_commit_msg_hook(root: Path, interpreter: str) -> Path:
        raise RuntimeError("a foreign commit-msg hook exists; left untouched")

    fake.install_commit_msg_hook = install_commit_msg_hook
    monkeypatch.setitem(sys.modules, "plumb.claims", fake)
    report = _install(repo)
    assert any("foreign commit-msg hook" in line for line in report.lines)


def test_launcher_selection(repo: Path) -> None:
    def which_none(name: str) -> None:
        return None

    assert install.choose_launcher(repo, "auto", which=which_none).kind == "uv"
    scripts = repo / ".venv" / ("Scripts" if install.IS_WINDOWS else "bin")
    scripts.mkdir(parents=True)
    exe = scripts / ("python.exe" if install.IS_WINDOWS else "python")
    exe.write_text("", encoding="utf-8")
    venv = install.choose_launcher(repo, "auto", which=which_none)
    assert venv.kind == "venv"
    rel = exe.relative_to(repo).as_posix()
    assert venv.hook_prefix == f'"$CLAUDE_PROJECT_DIR/{rel}" -m plumb'
    assert venv.agent_prefix == f"{rel} -m plumb"
    # plumb on PATH only because the project's own venv is active: still the venv launcher
    inside = str(scripts / "plumb.exe")
    assert install.choose_launcher(repo, "auto", which=lambda n: inside).kind == "venv"
    elsewhere = "C:/tools/bin/plumb.exe" if install.IS_WINDOWS else "/usr/local/bin/plumb"
    assert install.choose_launcher(repo, "auto", which=lambda n: elsewhere).kind == "path"
    assert install.choose_launcher(repo, "path", which=which_none).hook_prefix == "plumb"
    assert install.choose_launcher(repo, "uv", which=which_none).kind == "uv"


def test_dry_run_writes_nothing(repo: Path, no_claims) -> None:
    report = _install(repo, dry_run=True)
    assert not (repo / ".claude").exists() and not (repo / "CLAUDE.md").exists()
    assert report.changed and any("would" in line for line in report.lines)


def test_invalid_settings_json_is_not_clobbered(repo: Path, no_claims) -> None:
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(install.InstallError):
        _install(repo)
    assert (repo / ".claude" / "settings.json").read_text(encoding="utf-8") == "{not json"


def test_cli_hooks_install_and_alias(repo: Path, no_claims, capsys) -> None:
    from plumb.cli import main

    assert main(["hooks", "install", "--root", str(repo), "--launcher", "uv"]) == 0
    assert _commands(_settings(repo), "SessionStart") == [
        "uv run --no-sync plumb hook session-start"]
    assert main(["install", "claude-code", "--root", str(repo), "--launcher", "uv"]) == 0
    assert "unchanged" in capsys.readouterr().out
    assert main(["install", "codex", "--root", str(repo)]) == 2


# --- SHOULD items -----------------------------------------------------------------------


def test_uninstall_removes_only_plumb_entries(repo: Path, no_claims) -> None:
    claude = repo / ".claude"
    claude.mkdir()
    foreign = {"env": {"FOO": "1"}, "permissions": {"deny": ["Bash(rm -rf:*)"]},
               "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo bye"}]}]}}
    (claude / "settings.json").write_text(json.dumps(foreign), encoding="utf-8")
    (repo / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
    _install(repo)
    install.uninstall(repo)
    settings = _settings(repo)
    assert settings == foreign
    assert not (claude / "skills" / "plumb-records").exists()
    assert not (claude / "commands" / "plumb.md").exists()
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "# Project\n"


def test_hooks_status_reports_installed_parts(repo: Path, no_claims) -> None:
    before = install.status(repo)
    assert any("not installed" in line for line in before)
    _install(repo)
    after = "\n".join(install.status(repo))
    for part in ("session-start", "prompt", "post-edit", "stop", "statusLine",
                 "PLUMB_AGENT_SESSION", "deny rules", "skill", "CLAUDE.md"):
        assert part in after


@pytest.mark.sr("SR-278")
def test_slash_command_brief_why_impact(repo: Path, no_claims) -> None:
    _install(repo)
    text = (repo / ".claude" / "commands" / "plumb.md").read_text(encoding="utf-8")
    assert "$ARGUMENTS" in text
    for name in ("brief", "explain", "why", "impact"):
        assert f"Bash(uv run --no-sync plumb {name}:*)" in text


@pytest.mark.sr("SR-203")
def test_slash_command_routes_plain_language_explain(repo: Path, no_claims) -> None:
    """/plumb advertises explain with plain-language arguments, keeps why as an alias, and
    advertises only subcommands the CLI has (R9: the /plumb why bug)."""
    from plumb import cli

    _install(repo)
    text = (repo / ".claude" / "commands" / "plumb.md").read_text(encoding="utf-8")
    hint = next(line for line in text.splitlines() if line.startswith("argument-hint:"))
    assert "explain <anything>" in hint
    assert "why <ID|path>" not in text
    assert "uv run --no-sync plumb explain <their words>" in text
    advertised = {part.split()[0] for part in hint.split('"')[1].split("|")}
    # sp5 6.1: the six owner verbs, plain words accepted (SR-064 EX-3), plus the JEV judge
    # (setup, status, calibrate: SR-039, R14); SR-122: every typed verb the command answers
    assert advertised == {"status", "intent", "clarify", "explain", "review", "impact", "view",
                          "jev", "debug",   # SR-328, DEC-254: the owner asks for debug
                          "init", "go", "undo", "conflicts",   # approve: gone (SR-208)
                          "merge-check", "inflight"}
    for name in (advertised - {"go", "undo"}) | {"why", "show"}:       # go, undo: typed only
        assert name in cli.ROUTES, name
    assert "not available in this build" not in cli._HELP


@pytest.mark.sr("SR-200")
def test_claude_md_block_formalizes_each_request_and_asks_no_read_back(repo: Path,
                                                                       no_claims) -> None:
    """EX-12: the always-loaded block turns each request into proposed records for the judge
    and asks the owner to read nothing back."""
    _install(repo)
    text = " ".join((repo / "CLAUDE.md").read_text(encoding="utf-8").split())
    assert ("Formalize each request that changes the system into proposed records linked to "
            "the code it changes, for the judge to validate") in text
    assert "implemented_by" in text and "read nothing back" in text
    assert "read back each request" not in text.lower()
