"""From the per-repository install to the plugin (SP7 4.7; SR-084): the old install keeps working
and the plugin stays silent there; ``plumb plugin migrate`` removes only what plumb wrote, keeps
and names what the owner changed, and points git's checks at the user-level launcher."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from plumb.present import owner_text

from .helpers import (
    EVENTS,
    PLUGIN,
    adopted_repo,
    env_with,
    git,
    hook_data,
    needs_sh,
    ready_home,
    run_hook,
    sentinel_bin,
    user_launcher,
)

pytestmark = [pytest.mark.sr("SR-084")]
OWN_HOOK = {"type": "command", "command": "echo my own check"}


def _legacy(root: Path) -> Path:
    """``root`` set up the old way, plus settings of the owner's own."""
    from plumb.hosts.claude_code.install import install

    adopted_repo(root)
    plugin_root = os.environ.pop("PLUMB_PLUGIN_ROOT", None)  # the old install ran without it
    try:
        install(root, launcher="path")
    finally:
        if plugin_root is not None:
            os.environ["PLUMB_PLUGIN_ROOT"] = plugin_root
    path = root / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings.setdefault("permissions", {}).setdefault("allow", []).append("Bash(git status)")
    settings["hooks"].setdefault("Stop", []).append({"hooks": [OWN_HOOK]})
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (root / "CLAUDE.md").write_text("# My project\n\n" + (root / "CLAUDE.md").read_text(
        encoding="utf-8"), encoding="utf-8")
    return root


@pytest.fixture
def plugin_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("PLUMB_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setenv("PLUMB_HOME", str(home))
    user_launcher(home)
    return home


def _migrate(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    from plumb.cli import main

    assert main(["plugin", "migrate", "--root", str(root)]) == 0
    return capsys.readouterr().out


def test_removes_only_plumb_entries(tmp_path: Path, plugin_env: Path,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = _legacy(tmp_path / "repo")
    out = _migrate(root, capsys)
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"permissions": {"allow": ["Bash(git status)"]},
                        "hooks": {"Stop": [{"hooks": [OWN_HOOK]}]}}
    assert not (root / ".claude" / "commands" / "plumb.md").exists()
    assert not (root / ".claude" / "skills").exists()
    assert not (root / ".claude" / "plumb" / "gate.sh").exists()
    claude_md = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "plumb:begin" not in claude_md and claude_md.startswith("# My project")
    lines = out.splitlines()
    assert lines[0] == owner_text.MIGRATE_DONE
    assert owner_text.MIGRATE_KEPT_SETTINGS in lines
    assert ".claude" not in out  # plain words, no paths
    assert _migrate(root, capsys).strip() == owner_text.MIGRATE_NOTHING  # idempotent


def test_edited_copy_kept(tmp_path: Path, plugin_env: Path,
                          capsys: pytest.CaptureFixture[str]) -> None:
    root = _legacy(tmp_path / "repo")
    command = root / ".claude" / "commands" / "plumb.md"
    edited = command.read_text(encoding="utf-8") + "\nAlso say hello.\n"
    command.write_text(edited, encoding="utf-8")
    out = _migrate(root, capsys)
    assert command.read_text(encoding="utf-8") == edited
    assert owner_text.MIGRATE_KEPT.format(what="the /plumb command") in out.splitlines()
    assert not (root / ".claude" / "skills" / "plumb" / "SKILL.md").exists()


def test_hooks_repointed(tmp_path: Path, plugin_env: Path,
                         capsys: pytest.CaptureFixture[str]) -> None:
    from plumb import launcher

    root = _legacy(tmp_path / "repo")
    hooks = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip()) / "hooks"
    assert "-m plumb" in (hooks / "pre-push").read_text(encoding="utf-8")
    _migrate(root, capsys)
    for name in ("commit-msg", "pre-merge-commit", "prepare-commit-msg", "post-merge",
                 "pre-push"):
        text = (hooks / name).read_text(encoding="utf-8")
        assert launcher.user_launcher() in text and "-m plumb" not in text, name
    driver = git(root, "config", "--get", "merge.plumb-record.driver").stdout
    assert driver.startswith(f'"{launcher.user_launcher()}"')


@needs_sh
def test_legacy_repo_hooks_run_once(tmp_path: Path) -> None:
    """With the plugin active in a repository set up the old way, the plugin's hooks exit at
    once: the old install runs each check, so nothing runs twice (SR-084 EX-1)."""
    sentinel = tmp_path / "sentinel.txt"
    root = _legacy(tmp_path / "repo")
    poison = sentinel_bin(tmp_path / "poison", sentinel)
    home = ready_home(tmp_path / "home", poison / "python")
    env = env_with([poison], PLUMB_HOME=str(home), CLAUDE_PROJECT_DIR=str(root))
    for event in EVENTS:
        result = run_hook(event, root, hook_data(event), env)
        assert (result.returncode, result.stdout) == (0, ""), event
    assert not sentinel.exists()
