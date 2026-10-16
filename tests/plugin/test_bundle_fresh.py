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

pytestmark = [pytest.mark.sr("SR-279")]


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


def test_the_diagram_dependency_names_its_marketplace() -> None:
    # a bare "diagram" is looked up in plumb's own marketplace, where it is not: the update fails
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert manifest["dependencies"] == ["diagram@diagram-mod"]
    assert market["allowCrossMarketplaceDependenciesOn"] == ["diagram-mod"]


def test_hooks_cover_every_event() -> None:
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["modules"] == ["./register.tsx"]
    commands = {h["command"] for groups in hooks["hooks"].values() for g in groups
                for h in g["hooks"]}
    for event in ("session-start", "prompt", "pre-tool", "post-edit", "edit-check", "question-answer",
                  "stop"):
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


# SR-123: what the plugin ships, and what --check refuses

@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """build_plugin with its plugin and templates folders in ``tmp_path``."""
    module = _build_plugin()
    plugin, templates = tmp_path / "plugin", tmp_path / "templates"
    (templates / "skills").mkdir(parents=True)
    (plugin / "skills").mkdir(parents=True)
    monkeypatch.setattr(module, "PLUGIN", plugin)
    monkeypatch.setattr(module, "TEMPLATES", templates)
    monkeypatch.setattr(module, "ENGINE_TYPES", plugin / ".claude-plugin" / "types")
    return module


@pytest.mark.sr("SR-279")
def test_a_test_file_in_the_plugin_fails_the_check(isolated, capsys) -> None:
    """SR-123 EX-1: --check fails naming a *.test.tsx (and the harness, the fixtures)."""
    hooks = isolated.PLUGIN / "hooks"
    hooks.mkdir()
    for name in ("band.test.tsx", "harness.ts", "fixtures.ts", "register.tsx"):
        (hooks / name).write_text("//\n", encoding="utf-8")
    # what the engine lays beside a mod it loaded is not the plugin's
    laid = isolated.ENGINE_TYPES / "claude-code"
    laid.mkdir(parents=True)
    (laid / "fixtures.ts").write_text("//\n", encoding="utf-8")
    assert isolated.main(["--check"]) == 1
    out = capsys.readouterr().out
    named = [line for line in out.splitlines() if "test-only" in line]
    assert len(named) == 3
    for name in ("band.test.tsx", "harness.ts", "fixtures.ts"):
        assert any(line.startswith(f"{(hooks / name).as_posix()}:") for line in named), name


@pytest.mark.sr("SR-279")
def test_no_test_files_ship_in_the_plugin() -> None:
    assert _build_plugin().test_only_files() == []


@pytest.mark.sr("SR-279")
def test_every_hook_has_a_timeout() -> None:
    """Each hook is bounded; plumb's own watchdog (30 s, the stop read-back 1 s more) sits
    well inside each bound (DEC-078: 60 s, and 120 s for the stop and async hooks)."""
    from plumb.hosts.claude_code.hookio import HARD_LIMIT_S
    from plumb.hosts.claude_code.stop import STOP_GRACE_S

    hooks = json.loads(_build_plugin().hooks_json())["hooks"]
    timeouts = {h["command"].rsplit(" ", 1)[1]: h["timeout"]
                for groups in hooks.values() for g in groups for h in g["hooks"]}
    assert timeouts == {"session-start": 60, "prompt": 60, "pre-tool": 60, "edit-check": 60,
                        "post-edit": 120, "question-answer": 120, "stop": 120,
                        "subagent-stop": 120}
    assert all(t > HARD_LIMIT_S + STOP_GRACE_S for t in timeouts.values())
    post = hooks["PostToolUse"]
    assert [g["hooks"][0].get("async", False) for g in post] == [True, False, True]


@pytest.mark.sr("SR-279")
def test_skill_reference_files_are_rendered(isolated) -> None:
    skill = isolated.TEMPLATES / "skills" / "plumb-records"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("run `{plumb} status`\n", encoding="utf-8")
    (skill / "references" / "ids.md").write_bytes(b"`{plumb} show <ID>`\r\n")
    (skill / "references" / "table.csv").write_text("a,{plumb}\n", encoding="utf-8")
    skills = isolated.PLUGIN / "skills"
    files = {p.relative_to(isolated.PLUGIN).as_posix(): text
             for p, text in isolated.text_files().items() if skills in p.parents}
    assert files == {"skills/plumb-records/SKILL.md": "run `plumb status`\n",
                     "skills/plumb-records/references/ids.md": "`plumb show <ID>`\n",
                     "skills/plumb-records/references/table.csv": "a,{plumb}\n"}


@pytest.mark.sr("SR-279")
def test_a_renamed_skill_leaves_no_orphan(isolated) -> None:
    """A skill folder or reference with no template is stale, and the build removes it."""
    skill = isolated.TEMPLATES / "skills" / "plumb-records"
    skill.mkdir()
    (skill / "SKILL.md").write_text("new\n", encoding="utf-8")
    old = isolated.PLUGIN / "skills" / "plumb"
    (old / "references").mkdir(parents=True)
    (old / "SKILL.md").write_text("old\n", encoding="utf-8")
    (old / "references" / "gone.md").write_text("old\n", encoding="utf-8")
    kept = isolated.PLUGIN / "skills" / "plumb-records"
    kept.mkdir()
    (kept / "SKILL.md").write_text("new\n", encoding="utf-8")
    (kept / "dropped.md").write_text("old\n", encoding="utf-8")
    expected = isolated.text_files()
    found = {p.relative_to(isolated.PLUGIN).as_posix() for p in isolated.orphans(expected)}
    assert found == {"skills/plumb/SKILL.md", "skills/plumb/references/gone.md",
                     "skills/plumb-records/dropped.md"}
    isolated.remove_orphans(expected)
    assert not old.exists()
    assert sorted(p.name for p in kept.iterdir()) == ["SKILL.md"]
    assert (isolated.PLUGIN / "skills").is_dir()


@pytest.mark.sr("SR-279")
def test_the_plugin_ships_the_license() -> None:
    root = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert root.startswith("MIT License") and "Colin AUBE" in root
    assert _build_plugin().text_files()[PLUGIN / "LICENSE"] == root
    assert (PLUGIN / "README.md").is_file()


@pytest.mark.sr("SR-202")
def test_plugin_command_reads_the_references_beside_the_plugin() -> None:
    """In a plugin install the skills' reference files exist only under the plugin
    (`plumb plugin migrate` deletes the .claude copies): the command points there."""
    built = _build_plugin().text_files()[PLUGIN / "commands" / "plumb.md"]
    for name in ("conflicts.md", "merge.md"):
        assert f"${{CLAUDE_PLUGIN_ROOT}}/skills/plumb-records/references/{name}" in built
    assert ".claude/skills/" not in built


@pytest.mark.sr("SR-279")
@pytest.mark.parametrize("name", ["x.spec.tsx", "x_test.ts", "x.test.ts"])
def test_every_test_file_spelling_fails_the_check(isolated, name: str) -> None:
    mod = isolated.PLUGIN / "mod"
    mod.mkdir()
    (mod / name).write_text("//\n", encoding="utf-8")
    assert [p.name for p in isolated.test_only_files()] == [name]
