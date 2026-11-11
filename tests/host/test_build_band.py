"""SR-358: at every prompt iaso compares the plugin the session runs with iaso's local main (by
vendored source digest) and the plugin Claude Code installed with the main of iaso's repository
(by commit, as the local clone's history orders them) and notes one line per misalignment, with
both versions and the fix, for the band's red lines. A repository that is not known yet is noted
as unchecked, never red, and the hook never waits for it. Nothing is reinstalled."""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from iaso import build
from iaso.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-358")
URL = "https://github.com/Cols77/iaso"
REAL_LATEST = build._latest      # the `repository` fixture replaces it


def _manifest(folder: Path, digest: str) -> None:
    path = folder / "plugin" / "vendor" / "MANIFEST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source_digest": digest}), encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


def _build(repo: Path, digest: str) -> str:
    """A build of iaso committed in ``repo`` (iaso's local clone): its commit."""
    _manifest(repo, digest)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"build {digest}")
    return _git(repo, "rev-parse", "HEAD")


def _turn(repo: Path, hook_input) -> dict:
    payload = hook_input("UserPromptSubmit", prompt="hello there", session_id="s1")
    assert prompt.main(stdin=io.StringIO(payload), stdout=io.StringIO(), root=repo,
                       verify=FakeVerify(), backend=FakeBackend()) == 0
    return json.loads((repo / ".iaso" / "session" / "s1" / "build.json").read_text("utf-8"))


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> dict:
    """iaso's repository main: its ``commit``; "" when it is not known."""
    held = {"commit": ""}

    def latest(url: str) -> str:
        assert url == URL
        return held["commit"]
    monkeypatch.setattr(build, "_latest", latest)
    return held


@pytest.fixture
def loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repository):
    """``loaded(digest, installed=None)``: the plugin Claude Code runs, as the hooks'
    IASO_PLUGIN_ROOT names it; ``installed`` is the commit Claude Code recorded for it."""
    cached = tmp_path / "cache"
    (cached / "plugin" / ".claude-plugin").mkdir(parents=True)
    (cached / "plugin" / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"repository": URL}), encoding="utf-8")
    monkeypatch.setenv("IASO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)     # the session's own plugin
    monkeypatch.setenv("IASO_PLUGIN_ROOT", str(cached / "plugin"))
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])

    def load(digest: str, installed: str | None = None) -> None:
        _manifest(cached, digest)
        if installed:
            file = tmp_path / "claude" / "plugins" / "installed_plugins.json"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps({"version": 2, "plugins": {"iaso@iaso": [
                {"scope": "project", "projectPath": "elsewhere", "gitCommitSha": "other",
                 "installPath": str(cached / "plugin")},
                {"scope": "user", "gitCommitSha": installed,
                 "installPath": str(cached / "plugin")}]}}), encoding="utf-8")
    return load


def test_ex1_installed_plugin_behind_its_repository_the_band_gets_both_commits(
        repo: Path, loaded, repository, hook_input) -> None:
    first = _build(repo, "aaa-0000")
    repository["commit"] = _build(repo, "bbb-0000")
    loaded("bbb-0000", installed=first)
    line = (f"installed plugin {first[:7]} is behind its repository's "
            f"{repository['commit'][:7]}: update the plugin, then reload plugins")
    assert build.outdated(repo) == (True, line)
    assert _turn(repo, hook_input) == {"lines": [line], "unchecked": False}


def test_installed_plugin_ahead_of_its_repository_says_push(
        repo: Path, loaded, repository) -> None:
    repository["commit"] = _build(repo, "aaa-0000")
    second = _build(repo, "bbb-0000")
    loaded("bbb-0000", installed=second)
    assert build.check(repo)["lines"] == [
        f"installed plugin {second[:7]} is ahead of its repository's "
        f"{repository['commit'][:7]}: push main"]


def test_installed_plugin_without_a_local_clone_differs(
        repo: Path, loaded, repository) -> None:
    repository["commit"] = "f60c3556" + "0" * 32
    loaded("old-0000", installed="fead6e89" + "0" * 32)       # another repository
    assert build.check(repo)["lines"] == [
        "installed plugin fead6e8 differs from its repository's f60c355: update the plugin, "
        "then reload plugins"]


def test_ex2_installed_plugin_equal_to_its_repository_the_line_is_gone(
        repo: Path, loaded, repository, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    repository["commit"] = _build(repo, "aaa-0000")
    loaded("aaa-0000", installed=repository["commit"])
    assert build.outdated(repo) == (False, "")
    assert _turn(repo, hook_input) == {"lines": [], "unchecked": False}
    monkeypatch.delenv("IASO_PLUGIN_ROOT")                      # not run from a plugin
    assert build.check(repo)["lines"] == []


def test_a_loaded_folder_that_is_not_installed_is_compared_as_local_main(
        repo: Path, loaded, repository) -> None:
    repository["commit"] = _build(repo, "aaa-0000")
    loaded("aaa-0000")                                           # a dev folder, no record
    assert build.check(repo)["lines"] == []
    second = _build(repo, "bbb-0000")
    loaded("bbb-0000")
    assert build.check(repo)["lines"] == [
        f"local main {second[:7]} is ahead of its repository's "
        f"{repository['commit'][:7]}: push main"]
    assert build.outdated(repo) == (False, "")    # the plugin runs local main's build


def test_ex3_local_main_rebuilt_after_the_load_says_reload(
        repo: Path, loaded, repository, hook_input) -> None:
    _build(repo, "aaa-0000")
    repository["commit"] = _build(repo, "bbb-0000")
    loaded("aaa-0000")
    assert _turn(repo, hook_input)["lines"] == [
        "iaso aaa-000 is behind local main's bbb-000: reload plugins"]


def test_the_plugin_built_from_a_branch_is_ahead_of_local_main(
        repo: Path, loaded, repository) -> None:
    repository["commit"] = _build(repo, "aaa-0000")
    _git(repo, "checkout", "-q", "-b", "feat")
    _build(repo, "ccc-0000")
    _git(repo, "checkout", "-q", "main")
    loaded("ccc-0000")
    assert build.check(repo)["lines"] == [
        "iaso ccc-000 is ahead of local main's aaa-000 (built from another branch)"]


def test_ex5_an_unknown_repository_is_unchecked_not_red(
        repo: Path, loaded, hook_input) -> None:
    loaded("old-0000", installed="fead6e89" + "0" * 32)
    assert _turn(repo, hook_input) == {"lines": [], "unchecked": True}


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list:
    urls: list = []
    monkeypatch.setattr(build, "_spawn", urls.append)
    monkeypatch.setattr(build, "_fetch", lambda url: pytest.fail("the hook waited"))
    return urls


def _kept(commit: str, age: float) -> None:
    from iaso.launcher import iaso_home

    iaso_home().mkdir(parents=True, exist_ok=True)
    (iaso_home() / "latest.json").write_text(json.dumps(
        {"url": URL, "commit": commit, "at": time.time() - age}), encoding="utf-8")


def test_a_stale_cache_answers_at_once_and_refreshes_in_the_background(
        loaded, spawned) -> None:
    loaded("old-0000")
    _kept("stale-commit", build.KEEP_S + 1)
    assert REAL_LATEST(URL) == "stale-commit"
    assert spawned == [URL]
    assert REAL_LATEST(URL) == "stale-commit" and spawned == [URL]   # not once per prompt


def test_a_fresh_cache_spawns_nothing_and_a_missing_one_is_unknown(
        loaded, spawned) -> None:
    loaded("old-0000")
    assert REAL_LATEST(URL) == "" and spawned == [URL]
    spawned.clear()
    _kept("fresh-commit", 1)
    assert REAL_LATEST(URL) == "fresh-commit" and spawned == []


def test_the_refresh_keeps_the_commit_and_a_failure_only_for_a_short_while(
        loaded, spawned, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded("old-0000")
    monkeypatch.setattr(build, "_fetch", lambda url: "abc123")
    build._refresh(URL)
    assert REAL_LATEST(URL) == "abc123" and spawned == []
    monkeypatch.setattr(build, "_fetch", lambda url: "")
    build._refresh(URL)
    assert REAL_LATEST(URL) == "" and spawned == []             # failed: not retried yet
    _kept("", build.KEEP_S + 1)
    REAL_LATEST(URL)
    assert spawned == [URL]


def test_the_remote_commit_is_read_with_ls_remote_only(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "abc123\trefs/heads/main\n", "")
    monkeypatch.setattr(subprocess, "run", run)
    assert build._fetch(URL) == "abc123"
    assert calls == [["git", "ls-remote", URL, "refs/heads/main"]]

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 30)
    monkeypatch.setattr(subprocess, "run", timeout)
    assert build._fetch(URL) == ""
