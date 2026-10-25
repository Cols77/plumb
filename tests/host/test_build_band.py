"""SR-358: at every prompt plumb compares the plugin the session runs, plumb's local main and the
main of plumb's repository (by vendored source digest) and notes one line per misalignment, with
both versions and the fix, for the band's red lines; git history says which side is ahead. A
repository that cannot be read is noted as unchecked, never red. Nothing is reinstalled."""

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


def _manifest(folder: Path, digest: str) -> None:
    path = folder / "plugin" / "vendor" / "MANIFEST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source_digest": digest}), encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


def _build(repo: Path, digest: str) -> str:
    """A build of plumb committed in ``repo`` (plumb's local clone): its commit."""
    _manifest(repo, digest)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"build {digest}")
    return _git(repo, "rev-parse", "HEAD")


def _turn(repo: Path, hook_input) -> dict:
    payload = hook_input("UserPromptSubmit", prompt="hello there", session_id="s1")
    assert prompt.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo,
                       verify=FakeVerify(), backend=FakeBackend()) == 0
    return json.loads((repo / ".plumb" / "session" / "s1" / "build.json").read_text("utf-8"))


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> dict:
    """plumb's repository main: ``digest`` and ``commit``; "" when it cannot be read."""
    held = {"digest": "new-0000", "commit": "", "reads": 0}

    def fetch(url: str) -> tuple[str, str]:
        assert url == URL
        held["reads"] += 1
        return held["digest"], held["commit"]
    monkeypatch.setattr(build, "_fetch", fetch)
    return held


@pytest.fixture
def loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repository):
    """``loaded(digest)``: the plugin Claude Code runs, as the hooks' PLUMB_PLUGIN_ROOT names
    it."""
    cached = tmp_path / "cache"
    (cached / "plugin" / ".claude-plugin").mkdir(parents=True)
    (cached / "plugin" / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"repository": URL}), encoding="utf-8")
    monkeypatch.setenv("PLUMB_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)     # the session's own plugin
    monkeypatch.setenv("PLUMB_PLUGIN_ROOT", str(cached / "plugin"))
    monkeypatch.setattr(build, "KEEP_S", 0)                      # read the repository each time
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    return lambda digest: _manifest(cached, digest)


def test_ex1_the_repository_rebuilt_after_the_cache_the_band_gets_both_versions(
        repo: Path, loaded, hook_input) -> None:
    loaded("old-0000")                           # another repository: no local clone of plumb
    line = ("plumb old-000 differs from its repository's new-000: update the plugin, then "
            "reload plugins")
    assert build.outdated(repo) == (True, line)
    assert _turn(repo, hook_input) == {"lines": [line], "unchecked": False}


def test_ex2_the_plugin_updated_the_line_is_gone(
        repo: Path, loaded, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded("old-0000")
    assert _turn(repo, hook_input)["lines"]
    loaded("new-0000")                                           # the owner updated plumb
    assert build.outdated(repo) == (False, "")
    assert _turn(repo, hook_input) == {"lines": [], "unchecked": False}
    monkeypatch.delenv("PLUMB_PLUGIN_ROOT")                      # not run from a plugin
    assert build.check(repo)["lines"] == []


def test_ex3_local_main_rebuilt_after_the_load_says_reload(
        repo: Path, loaded, repository, hook_input) -> None:
    _build(repo, "aaa-0000")
    repository.update(digest="bbb-0000", commit=_build(repo, "bbb-0000"))
    loaded("aaa-0000")
    assert _turn(repo, hook_input)["lines"] == [
        "plumb aaa-000 is behind local main's bbb-000: reload plugins"]


def test_the_plugin_built_from_a_branch_is_ahead_of_local_main(
        repo: Path, loaded, repository) -> None:
    repository.update(digest="aaa-0000", commit=_build(repo, "aaa-0000"))
    _git(repo, "checkout", "-q", "-b", "feat")
    _build(repo, "ccc-0000")
    _git(repo, "checkout", "-q", "main")
    loaded("ccc-0000")
    assert build.check(repo)["lines"] == [
        "plumb ccc-000 is ahead of local main's aaa-000 (built from another branch)"]


def test_ex4_local_main_ahead_of_the_repository_says_push(
        repo: Path, loaded, repository) -> None:
    repository.update(digest="aaa-0000", commit=_build(repo, "aaa-0000"))
    _build(repo, "bbb-0000")
    loaded("bbb-0000")
    assert build.check(repo)["lines"] == [
        "local main bbb-000 is ahead of its repository's aaa-000: push main"]
    assert build.outdated(repo) == (False, "")    # the plugin runs local main's build


def test_ex5_an_unreadable_repository_is_unchecked_not_red(
        repo: Path, loaded, repository, hook_input) -> None:
    repository.update(digest="")
    loaded("old-0000")
    assert _turn(repo, hook_input) == {"lines": [], "unchecked": True}


def test_the_repository_is_read_at_most_once_a_while(
        repo: Path, loaded, repository, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, "KEEP_S", 900)
    loaded("old-0000")
    build.check(repo)
    build.check(repo)
    assert repository["reads"] == 1
