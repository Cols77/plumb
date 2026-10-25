"""SR-358: when the plumb build Claude Code runs (the loaded plugin's vendored source digest)
differs from the one on plumb's repository's main, whatever the install route and the session's
repository, the prompt hook notes both for the band's red line; once the plugin is updated the
note clears. A repository that cannot be read is noted as unchecked, never red. Nothing is
reinstalled."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from plumb import build
from plumb.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-358")
URL = "https://github.com/Cols77/plumb"


def _manifest(folder: Path, digest: str) -> Path:
    path = folder / "plugin" / "vendor" / "MANIFEST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source_digest": digest}), encoding="utf-8")
    return path


def _turn(repo: Path, hook_input) -> dict:
    payload = hook_input("UserPromptSubmit", prompt="hello there", session_id="s1")
    assert prompt.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo,
                       verify=FakeVerify(), backend=FakeBackend()) == 0
    return json.loads((repo / ".plumb" / "session" / "s1" / "build.json").read_text("utf-8"))


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> dict:
    """plumb's repository: ``{"digest": ...}`` is its main's build; "" cannot be read."""
    held = {"digest": "new", "reads": 0}

    def fetch(url: str) -> str:
        assert url == URL
        held["reads"] += 1
        return held["digest"]
    monkeypatch.setattr(build, "_fetch", fetch)
    return held


@pytest.fixture
def loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repository) -> Path:
    """The plugin Claude Code cached, as the hooks' PLUMB_PLUGIN_ROOT names it."""
    cached = tmp_path / "cache"
    _manifest(cached, "old")
    (cached / "plugin" / ".claude-plugin").mkdir()
    (cached / "plugin" / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"repository": URL}), encoding="utf-8")
    monkeypatch.setenv("PLUMB_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)     # the session's own plugin
    monkeypatch.setenv("PLUMB_PLUGIN_ROOT", str(cached / "plugin"))
    monkeypatch.setattr(build, "KEEP_S", 0)                      # read the repository each time
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    return cached


def test_ex1_the_repository_rebuilt_after_the_cache_the_band_gets_both_versions(
        repo: Path, loaded: Path, hook_input) -> None:
    assert build.outdated(repo) == (True, "running old, repository new")
    assert _turn(repo, hook_input) == {"outdated": True, "unchecked": False,
                                       "running": "old", "latest": "new"}


def test_ex1_the_session_repositorys_own_main_is_not_the_reference(
        repo: Path, loaded: Path, repository, hook_input) -> None:
    _manifest(repo, "other")                     # plumb's checkout or any repository's own build
    for args in (("add", "-A"), ("commit", "-q", "-m", "a build")):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    repository["digest"] = "old"
    assert build.outdated(repo) == (False, "")
    assert _turn(repo, hook_input)["outdated"] is False


def test_ex2_the_plugin_updated_the_line_is_gone(
        repo: Path, loaded: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _turn(repo, hook_input)["outdated"] is True
    _manifest(loaded, "new")                                     # the owner updated plumb
    assert build.outdated(repo) == (False, "")
    assert _turn(repo, hook_input)["outdated"] is False
    monkeypatch.delenv("PLUMB_PLUGIN_ROOT")                      # not run from a plugin
    assert build.check(repo)["state"] == ""


def test_an_unreadable_repository_is_unchecked_not_red(
        repo: Path, loaded: Path, repository, hook_input) -> None:
    repository["digest"] = ""
    assert build.outdated(repo) == (False, "")
    assert _turn(repo, hook_input) == {"outdated": False, "unchecked": True,
                                       "running": "old", "latest": ""}


def test_the_repository_is_read_at_most_once_a_while(
        repo: Path, loaded: Path, repository, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, "KEEP_S", 900)
    build.check(repo)
    build.check(repo)
    assert repository["reads"] == 1
