"""SR-397 EX-10, report-f5491971: one lookup of the installed claude command, PATH first, then
the folders its installers use, so a process started with a PATH that lost it still finds it."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.hosts.claude_code import claude_binary
from iaso.understand.dispatch.claude_code import ClaudeCodeDispatcher

pytestmark = pytest.mark.sr("SR-397")


def _claude(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    binary = folder / "claude"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")   # the launching PATH lost claude's folder
    return home


def test_a_lost_path_still_finds_claude_in_its_install_folder(home: Path) -> None:
    installed = _claude(home / ".npm-global" / "bin")
    assert claude_binary() == str(installed)
    # the fixer's model calls go through the dispatcher's lookup, given the worker's own env
    assert ClaudeCodeDispatcher(env={"PATH": "/usr/bin:/bin"}).available() is None


def test_the_path_comes_first_and_nothing_installed_is_none(home: Path, tmp_path: Path) -> None:
    on_path = _claude(tmp_path / "on-path")
    _claude(home / ".local" / "bin")
    assert claude_binary(str(on_path.parent)) == str(on_path)
    assert claude_binary(str(tmp_path / "empty")) == str(home / ".local" / "bin" / "claude")
    (home / ".local" / "bin" / "claude").unlink()
    assert claude_binary() is None
