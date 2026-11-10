"""``/iaso init`` under the plugin (SP7 4.5; SR-083 EX-1, EX-2): iaso's record folder and git's
checks, each calling the user-level launcher; nothing under ``.claude/``, no ``CLAUDE.md``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from iaso.present import owner_text

from .helpers import PLUGIN, git, git_repo, needs_sh, user_launcher

pytestmark = [pytest.mark.sr("SR-280")]
HOOKS = ("commit-msg", "pre-merge-commit", "prepare-commit-msg", "post-merge", "pre-push")


@pytest.fixture
def plugin_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("IASO_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setenv("IASO_HOME", str(home))
    user_launcher(home)
    return home


def _init(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    from iaso.cli import main

    assert main(["init", "--root", str(root)]) == 0
    return capsys.readouterr().out


def _hooks(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip()) / "hooks"


def test_claude_dir_untouched(tmp_path: Path, plugin_home: Path,
                              capsys: pytest.CaptureFixture[str]) -> None:
    root = git_repo(tmp_path / "repo")
    out = _init(root, capsys)
    assert (root / ".iaso" / "config.yaml").is_file()
    assert not (root / ".claude").exists()
    assert not (root / "CLAUDE.md").exists()
    assert out.strip() == owner_text.INIT_DONE
    assert _init(root, capsys).strip() == owner_text.INIT_DONE  # idempotent


def test_git_hooks_written(tmp_path: Path, plugin_home: Path,
                           capsys: pytest.CaptureFixture[str]) -> None:
    from iaso import launcher

    root = git_repo(tmp_path / "repo")
    _init(root, capsys)
    for name in HOOKS:
        text = (_hooks(root) / name).read_text(encoding="utf-8")
        assert launcher.user_launcher() in text, name
    assert "merge=iaso-record" in (root / ".iaso" / ".gitattributes").read_text(
        encoding="utf-8")
    assert git(root, "config", "--get", "merge.iaso-record.driver").stdout.strip()


def _commit_env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("IASO_PLUGIN_ROOT", None)  # git's hooks get it from the launcher, not the session
    env["IASO_HOME"] = str(home)
    return env


def _commit(root: Path, message: str, env: dict[str, str]):
    (root / "file.txt").write_text(message, encoding="utf-8")
    git(root, "add", "-A", env=env)
    return git(root, "commit", "-q", "-m", message, env=env, check=False)


@needs_sh
def test_commit_msg_holds_missing_trailer(tmp_path: Path, plugin_home: Path,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = git_repo(tmp_path / "repo")
    _init(root, capsys)
    env = _commit_env(plugin_home)
    held = _commit(root, "change\n\nSR: SR-999\n", env)
    assert held.returncode != 0
    assert "SR-999" in held.stdout + held.stderr
    assert _commit(root, "an ordinary change\n", env).returncode == 0


def test_foreign_hook_kept(tmp_path: Path, plugin_home: Path,
                           capsys: pytest.CaptureFixture[str]) -> None:
    root = git_repo(tmp_path / "repo")
    hooks = _hooks(root)
    hooks.mkdir(parents=True, exist_ok=True)
    own = "#!/bin/sh\necho my own push check\n"
    (hooks / "pre-push").write_text(own, encoding="utf-8")
    out = _init(root, capsys)
    assert (hooks / "pre-push").read_text(encoding="utf-8") == own
    assert owner_text.FOREIGN_PREPUSH_HOOK in out
    assert out.splitlines()[0] == owner_text.INIT_DONE


@needs_sh
def test_hook_without_plugin_passes_with_line(tmp_path: Path, plugin_home: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    """A teammate's machine without the plugin: the hook says one plain line and lets the
    commit through (the merge boundary at push catches what it skipped)."""
    root = git_repo(tmp_path / "repo")
    _init(root, capsys)
    (plugin_home / "bin" / "iaso").unlink()
    result = _commit(root, "change\n\nSR: SR-999\n", _commit_env(plugin_home))
    assert result.returncode == 0, result.stderr
    assert "iaso is not set up on this machine; this commit was not checked" in (
        result.stdout + result.stderr)
