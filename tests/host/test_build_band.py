"""SR-358: when the plumb build Claude Code runs (the loaded plugin's vendored source digest)
differs from main's, the prompt hook notes it for the band's red line; once the session runs
main's build the note clears. Nothing is reinstalled."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fakes import FakeBackend, FakeVerify

from plumb import build
from plumb.hosts.claude_code import prompt

pytestmark = pytest.mark.sr("SR-358")


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
def loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The plugin Claude Code cached, as the hooks' PLUMB_PLUGIN_ROOT names it."""
    cached = tmp_path / "cache"
    _manifest(cached, "old")
    monkeypatch.setenv("PLUMB_PLUGIN_ROOT", str(cached / "plugin"))
    monkeypatch.setattr(prompt, "understand_lines", lambda ctx, core, digest, text: [])
    return cached


def test_ex1_main_rebuilt_after_the_cache_the_band_gets_the_red_line(
        repo: Path, loaded: Path, hook_input) -> None:
    _manifest(repo, "new")
    old, built = build.outdated(repo)
    assert old and len(built) == 10 and built[4] == "-"          # main's build date
    note = _turn(repo, hook_input)
    assert note == {"outdated": True, "built": built}


def test_ex2_the_session_runs_mains_build_the_line_is_gone(
        repo: Path, loaded: Path, hook_input, monkeypatch: pytest.MonkeyPatch) -> None:
    _manifest(repo, "new")
    assert _turn(repo, hook_input)["outdated"] is True
    _manifest(loaded, "new")                                     # the owner reloaded plugins
    assert build.outdated(repo) == (False, "")
    assert _turn(repo, hook_input) == {"outdated": False, "built": ""}
    monkeypatch.delenv("PLUMB_PLUGIN_ROOT")                      # not run from a plugin
    assert build.outdated(repo) == (False, "")
