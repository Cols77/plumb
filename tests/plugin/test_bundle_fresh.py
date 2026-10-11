"""The plugin's GENERATED files and its vendored wheel match their sources (SP7 4.1): the
command, the skills, the edit gate, the mod's guard table, the hooks and manifests, and the wheel
built from ``src/plumb``. A failure here means: run ``python scripts/build_plugin.py``."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from plumb.present import owner_text

from .helpers import PLUGIN, REPO

pytestmark = [pytest.mark.sr("SR-082")]


def _build_plugin():
    spec = importlib.util.spec_from_file_location("build_plugin", REPO / "scripts" /
                                                  "build_plugin.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_fresh() -> None:
    assert _build_plugin().stale() == []


def test_versions_agree() -> None:
    from plumb import __version__

    version = re.search(r'^version\s*=\s*"([^"]+)"',
                        (REPO / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "plumb" and manifest["version"] == version == __version__
    assert market["plugins"][0]["source"] == "./plugin"
    assert market["plugins"][0]["version"] == version


def test_hooks_cover_every_event() -> None:
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["modules"] == ["./register.tsx"]
    commands = {h["command"] for groups in hooks["hooks"].values() for g in groups
                for h in g["hooks"]}
    for event in ("session-start", "prompt", "pre-tool", "post-edit", "edit-check", "stop"):
        assert f'sh "${{CLAUDE_PLUGIN_ROOT}}/bin/plumb-hook" {event}' in commands
    pre_tool = hooks["hooks"]["PreToolUse"][0]["matcher"].split("|")
    assert {"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"} <= set(pre_tool)


@pytest.mark.parametrize("line", ["NOT_ADOPTED", "GETTING_READY", "NEEDS_PYTHON"])
def test_shell_lines_are_the_owner_texts(line: str) -> None:
    """The sh hooks print the same plain lines plumb's Python names (one wording)."""
    text = (PLUGIN / "bin" / "plumb-hook").read_text(encoding="utf-8")
    assert getattr(owner_text, line) in text


def test_scripts_are_lf() -> None:
    for name in ("plumb", "plumb-hook", "gate.sh"):
        assert b"\r\n" not in (PLUGIN / "bin" / name).read_bytes(), name


def test_no_project_copies_in_the_plugin_command() -> None:
    """The command and skills name `plumb` (on the agent's PATH), never a repository's .venv."""
    for path in [PLUGIN / "commands" / "plumb.md", *(PLUGIN / "skills").glob("*/SKILL.md")]:
        text = path.read_text(encoding="utf-8")
        assert ".venv" not in text and "{plumb}" not in text, path
        assert not Path(path).read_bytes().startswith(b"\xef\xbb\xbf")
