"""Shared fixtures for every lane (spec 12.4): ``repo``, ``write_record``, ``hook_input``."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

# A worktree's tests import the worktree's own source, not the install the venv points at.
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if sys.path[:1] != [_SRC]:
    sys.path.insert(0, _SRC)
for _name in [n for n in sys.modules if n == "plumb" or n.startswith("plumb.")]:
    if not str(getattr(sys.modules[_name], "__file__", "") or "").startswith(_SRC):
        del sys.modules[_name]

pytest_plugins = ["loadbound"]

_KIND_DIRS = {"INT": "intents", "SR": "requirements", "DEC": "decisions", "FEAT": "features",
              "NC": "ncs"}
_ID_LINE = re.compile(r"^id:\s*['\"]?((?:INT|SR|DEC|FEAT|NC)-\d+)", re.MULTILINE)


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` and return stdout (raises on failure)."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            check=True, encoding="utf-8")
    return result.stdout


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--browser", action="store_true",
                     help="also collect tests/browser, the browser workspace lane")


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """The browser workspace lane runs only when asked for: ``--browser``, or its path named
    (an argument's own parents are never asked here, so ``pytest tests/browser`` still runs)."""
    if collection_path.name == "browser" and collection_path.parent.name == "tests":
        return not config.getoption("--browser")
    return None


@pytest.fixture(autouse=True)
def owner_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test process stands in for the owner's interactive terminal: every owner-only
    question (``approvals.require_owner``) is answered "y". The guard's own tests
    (``tests/core/test_owner_terminal.py``) restore the real terminal check."""
    from plumb import approvals

    monkeypatch.setattr(approvals, "owner_terminal_answer", lambda question: "y")
    # The agent's session marker, set by the host for every command an agent runs, must not
    # leak in: a test that needs it sets it itself.
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)


# Variable families the machine running the tests may set; none may reach a test.
_ISOLATED_PREFIXES = ("CLAUDE_", "PLUMB_", "CODEX_", "HERMES_", "GITHEAD_")
_CREDENTIAL_PREFIXES = ("TYPESAFE_", "OPENROUTER_")


@pytest.fixture(autouse=True)
def isolated_environment(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory,
                         monkeypatch: pytest.MonkeyPatch) -> None:
    """The one choke point for where a test runs: every host and plumb variable of the outer
    environment is removed, and the home directory (HOME, USERPROFILE, PLUMB_HOME) points
    into a temp dir, so no test reads the machine's real settings or credentials. The
    ``jev_live`` tests alone keep the real credentials and home (they call the live service)."""
    live = request.node.get_closest_marker("jev_live") is not None
    prefixes = _ISOLATED_PREFIXES if live else _ISOLATED_PREFIXES + _CREDENTIAL_PREFIXES
    for name in list(os.environ):
        if name.upper().startswith(prefixes):
            monkeypatch.delenv(name)
    if live:
        return
    home = tmp_path_factory.mktemp("home")
    for name in ("HOME", "USERPROFILE", "PLUMB_HOME"):
        monkeypatch.setenv(name, str(home))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)


@pytest.fixture(autouse=True)
def jev_user_files(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory,
                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never read the real user-level JEV files (``~/.config/plumb/jev`` and
    ``jev.json``); only ``jev_live`` tests do, so a configured machine runs them."""
    if request.node.get_closest_marker("jev_live"):
        return
    from plumb.judgment import jev

    home = tmp_path_factory.mktemp("user-config")
    monkeypatch.setattr(jev, "user_store_path", lambda: home / "jev")
    monkeypatch.setattr(jev, "user_config_path", lambda: home / "jev.json")


@pytest.fixture(autouse=True)
def every_record_is_the_sessions_work(request: pytest.FixtureRequest,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-361: a session is asked only about records its branch changes; most tests' scratch
    repository sits on its default branch, so every record counts as its work there. Only
    ``work_scope`` tests run the real branch rule."""
    if request.node.get_closest_marker("work_scope"):
        return
    from plumb.understand import judge

    monkeypatch.setattr(judge, "work_ids", lambda core: set(core.index()))


@pytest.fixture(autouse=True)
def main_checkout_is_not_guarded(request: pytest.FixtureRequest,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-384: most tests' scratch repository sits on its default branch and calls the hooks;
    only ``main_guard`` tests run the real guard of main's checkout."""
    if request.node.get_closest_marker("main_guard"):
        return
    from plumb import main_guard

    monkeypatch.setattr(main_guard, "main_checkout", lambda directory, root: None)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary git repository adopted by plumb (``.plumb/`` dirs) with one commit."""
    from plumb.commands import init_repo

    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    init_repo(root)
    (root / "README.md").write_text("test repo\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")
    return root


def _write_record(repo: Path, text: str, name: str | None = None) -> Path:
    match = _ID_LINE.search(text)
    if match is None:
        raise ValueError("record text has no id line")
    record_id = match.group(1)
    directory = repo / ".plumb" / _KIND_DIRS[record_id.split("-")[0]]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or f"{record_id}.md")
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.fixture
def write_record() -> Callable[..., Path]:
    """``write_record(repo, text)`` writes a record file into the kind's directory."""
    return _write_record


@pytest.fixture
def hook_input() -> Callable[..., str]:
    """``hook_input(event, **fields)`` returns Claude Code hook stdin JSON."""

    def build(event: str, **fields: object) -> str:
        data: dict[str, object] = {
            "session_id": "test-session",
            "transcript_path": "",
            "cwd": ".",
            "hook_event_name": event,
        }
        data.update(fields)
        return json.dumps(data)

    return build
