"""The plugin's GENERATED files and its vendored wheel match their sources (SP7 4.1): the
command, the skills, the edit gate, the mod's guard table, the hooks and manifests, and the wheel
built from ``src/iaso``. A failure here means: run ``python scripts/build_plugin.py``."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from iaso.present import owner_text

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
    from iaso import __version__

    version = re.search(r'^version\s*=\s*"([^"]+)"',
                        (REPO / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "iaso" and manifest["version"] == version == __version__
    assert market["plugins"][0]["source"] == "./plugin"
    assert market["plugins"][0]["version"] == version


def test_the_diagram_dependency_names_its_marketplace() -> None:
    # a bare "diagram" is looked up in iaso's own marketplace, where it is not: the update fails
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
        assert f'sh "${{CLAUDE_PLUGIN_ROOT}}/bin/iaso-hook" {event}' in commands
    pre_tool = hooks["hooks"]["PreToolUse"][0]["matcher"].split("|")
    assert {"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"} <= set(pre_tool)
    assert {"Read", "Grep", "Glob", "Agent", "Task"} <= set(pre_tool)   # SR-395


@pytest.mark.parametrize("line", ["NOT_ADOPTED", "GETTING_READY", "NEEDS_PYTHON"])
def test_shell_lines_are_the_owner_texts(line: str) -> None:
    """The sh hooks print the same plain lines iaso's Python names (one wording)."""
    text = (PLUGIN / "bin" / "iaso-hook").read_text(encoding="utf-8")
    assert getattr(owner_text, line) in text


def test_scripts_are_lf() -> None:
    for name in ("iaso", "iaso-hook", "gate.sh"):
        assert b"\r\n" not in (PLUGIN / "bin" / name).read_bytes(), name


def test_no_project_copies_in_the_plugin_command() -> None:
    """The command and skills name `iaso` (on the agent's PATH), never a repository's .venv."""
    for path in [PLUGIN / "commands" / "iaso.md", *(PLUGIN / "skills").glob("*/SKILL.md")]:
        text = path.read_text(encoding="utf-8")
        assert ".venv" not in text and "{iaso}" not in text, path
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
    """Each hook is bounded; iaso's own watchdog (90 s, the stop read-back 1 s more) sits
    inside each bound (SR-310: 120 s), except pre-tool and edit-check, 10 s (SR-379)."""
    from iaso.hosts.claude_code.hookio import HARD_LIMIT_S
    from iaso.hosts.claude_code.stop import STOP_GRACE_S

    hooks = json.loads(_build_plugin().hooks_json())["hooks"]
    timeouts = {h["command"].rsplit(" ", 1)[1]: h["timeout"]
                for groups in hooks.values() for g in groups for h in g["hooks"]}
    assert timeouts == {"session-start": 120, "prompt": 120, "pre-tool": 10, "edit-check": 10,
                        "post-edit": 120, "question-answer": 120, "stop": 120,
                        "subagent-stop": 120, "session-end": 120}
    assert all(t > HARD_LIMIT_S + STOP_GRACE_S for n, t in timeouts.items()
               if n not in ("pre-tool", "edit-check"))
    post = hooks["PostToolUse"]
    assert [g["hooks"][0].get("async", False) for g in post] == [True, False, True]


@pytest.mark.sr("SR-279")
def test_skill_reference_files_are_rendered(isolated) -> None:
    skill = isolated.TEMPLATES / "skills" / "iaso-records"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("run `{iaso} status`\n", encoding="utf-8")
    (skill / "references" / "ids.md").write_bytes(b"`{iaso} show <ID>`\r\n")
    (skill / "references" / "table.csv").write_text("a,{iaso}\n", encoding="utf-8")
    skills = isolated.PLUGIN / "skills"
    files = {p.relative_to(isolated.PLUGIN).as_posix(): text
             for p, text in isolated.text_files().items() if skills in p.parents}
    assert files == {"skills/iaso-records/SKILL.md": "run `iaso status`\n",
                     "skills/iaso-records/references/ids.md": "`iaso show <ID>`\n",
                     "skills/iaso-records/references/table.csv": "a,{iaso}\n"}


@pytest.mark.sr("SR-279")
def test_a_renamed_skill_leaves_no_orphan(isolated) -> None:
    """A skill folder or reference with no template is stale, and the build removes it."""
    skill = isolated.TEMPLATES / "skills" / "iaso-records"
    skill.mkdir()
    (skill / "SKILL.md").write_text("new\n", encoding="utf-8")
    old = isolated.PLUGIN / "skills" / "iaso"
    (old / "references").mkdir(parents=True)
    (old / "SKILL.md").write_text("old\n", encoding="utf-8")
    (old / "references" / "gone.md").write_text("old\n", encoding="utf-8")
    kept = isolated.PLUGIN / "skills" / "iaso-records"
    kept.mkdir()
    (kept / "SKILL.md").write_text("new\n", encoding="utf-8")
    (kept / "dropped.md").write_text("old\n", encoding="utf-8")
    expected = isolated.text_files()
    found = {p.relative_to(isolated.PLUGIN).as_posix() for p in isolated.orphans(expected)}
    assert found == {"skills/iaso/SKILL.md", "skills/iaso/references/gone.md",
                     "skills/iaso-records/dropped.md"}
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
    (`iaso plugin migrate` deletes the .claude copies): the command points there."""
    built = _build_plugin().text_files()[PLUGIN / "commands" / "iaso.md"]
    for name in ("conflicts.md", "merge.md"):
        assert f"${{CLAUDE_PLUGIN_ROOT}}/skills/iaso-records/references/{name}" in built
    assert ".claude/skills/" not in built


@pytest.mark.sr("SR-279")
@pytest.mark.parametrize("name", ["x.spec.tsx", "x_test.ts", "x.test.ts"])
def test_every_test_file_spelling_fails_the_check(isolated, name: str) -> None:
    mod = isolated.PLUGIN / "mod"
    mod.mkdir()
    (mod / name).write_text("//\n", encoding="utf-8")
    assert [p.name for p in isolated.test_only_files()] == [name]


# SR-377: the version is the git commit count, written to the five places

def _scratch_repo(tmp_path: Path, commits: int) -> Path:
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "src" / "iaso").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "src" / "iaso" / "__init__.py").write_text('__version__ = "0.1.0"\n',
                                                            encoding="utf-8")
    git("init", "-q")
    for n in range(commits):
        git("commit", "-q", "--allow-empty", "-m", f"c{n}")
    return tmp_path


@pytest.mark.sr("SR-377")
def test_version_is_commit_count(tmp_path: Path) -> None:
    """SR-377 EX-1: a repository with N commits builds 0.1.N."""
    assert _build_plugin().derived_version(_scratch_repo(tmp_path, 3)) == "0.1.3"


@pytest.mark.sr("SR-377")
def test_new_commit_raises_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-377 EX-1: one more commit, and the five places read 0.1.N+1."""
    import subprocess

    module = _build_plugin()
    repo = _scratch_repo(tmp_path, 2)
    monkeypatch.setattr(module, "REPO", repo)
    monkeypatch.setattr(module, "SRC", repo / "src" / "iaso")
    module.set_version(module.derived_version())
    assert module.version() == "0.1.2"
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "more"], cwd=repo, check=True, capture_output=True)
    module.set_version(module.derived_version())
    assert module.version() == "0.1.3"
    assert '__version__ = "0.1.3"' in (repo / "src" / "iaso" / "__init__.py").read_text()
    assert json.loads(module.plugin_json())["version"] == "0.1.3"
    assert json.loads(module.marketplace_json())["plugins"][0]["version"] == "0.1.3"
    assert module.wheel_name() == "iaso-0.1.3-py3-none-any.whl"   # the manifest names it


@pytest.mark.sr("SR-377")
def test_check_names_disagreeing_places(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys) -> None:
    """SR-377 EX-3: a place that says another version fails --check, named."""
    module = _build_plugin()
    repo = _scratch_repo(tmp_path, 1)
    (repo / "src" / "iaso" / "__init__.py").write_text('__version__ = "0.9.9"\n', encoding="utf-8")
    monkeypatch.setattr(module, "REPO", repo)
    monkeypatch.setattr(module, "SRC", repo / "src" / "iaso")
    plugin = repo / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"version": "0.5.5"}\n',
                                                           encoding="utf-8")
    monkeypatch.setattr(module, "PLUGIN", plugin)
    monkeypatch.setattr(module, "VENDOR", plugin / "vendor")
    monkeypatch.setattr(module, "text_files", lambda: {
        plugin / ".claude-plugin" / "plugin.json": module.plugin_json()})
    assert module.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "plugin.json: differs" in out and "__init__.py: version differs" in out


@pytest.mark.sr("SR-380")
@pytest.mark.parametrize("argv", [["view"], ["import", "pi-agent-factory", "x"], ["mcp", "serve"],
                                  ["triage"], ["spec", "approve", "INT-001"]])
def test_removed_verbs_are_unknown(argv: list[str], capsys) -> None:
    """SR-380 EX-1: the removed commands do not exist."""
    from iaso import cli

    try:
        code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code
    err = capsys.readouterr().err
    assert code == 2 and ("unknown command" in err or "invalid choice" in err)


@pytest.mark.sr("SR-380")
def test_wheel_requires_pyyaml_only() -> None:
    """SR-380 EX-4: installing iaso pulls PyYAML only; Manim is the extra iaso[video]."""
    import zipfile

    [wheel] = (PLUGIN / "vendor").glob("iaso-*.whl")
    with zipfile.ZipFile(wheel) as z:
        meta = z.read(next(n for n in z.namelist() if n.endswith("METADATA"))).decode("utf-8")
    required = [line.split(": ", 1)[1] for line in meta.splitlines()
                if line.startswith("Requires-Dist: ")]
    assert [r for r in required if "extra ==" not in r] == ["pyyaml>=6"]
    assert any(r.startswith("manim") and "extra == 'video'" in r for r in required)


def _commit_versions(repo: Path, pyproject: str | None = None, manifest: str | None = None) -> None:
    """Commit ``pyproject.toml`` and ``plugin/vendor/MANIFEST.json`` saying the given versions."""
    import subprocess

    if pyproject:
        (repo / "pyproject.toml").write_text(f'[project]\nversion = "{pyproject}"\n',
                                             encoding="utf-8")
    if manifest:
        (repo / "plugin" / "vendor").mkdir(parents=True, exist_ok=True)
        (repo / "plugin" / "vendor" / "MANIFEST.json").write_text(
            json.dumps({"version": manifest}), encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-q", "-m", "versions"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo,
                       check=True, capture_output=True)


@pytest.mark.sr("SR-377")
def test_version_never_below_the_head_version(tmp_path: Path) -> None:
    """SR-377: a checkout with fewer commits than its base builds the base's version, not lower."""
    repo = _scratch_repo(tmp_path, 2)
    _commit_versions(repo, pyproject="0.1.50", manifest="0.1.60")   # count is 3
    assert _build_plugin().derived_version(repo) == "0.1.60"
    _commit_versions(repo, pyproject="0.1.2", manifest="0.1.2")
    assert _build_plugin().derived_version(repo) == "0.1.4"          # count 4 wins over the floor


@pytest.mark.sr("SR-377")
def test_version_never_below_the_main_branch(tmp_path: Path) -> None:
    """SR-377: with a main ref, the version is at least what main committed."""
    import subprocess

    repo = _scratch_repo(tmp_path, 1)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "checkout", "-q", "-b", "main"], cwd=repo, check=True,
                   capture_output=True)
    _commit_versions(repo, pyproject="0.1.90", manifest="0.1.90")
    subprocess.run([*git, "checkout", "-q", "-b", "work", "HEAD~1"], cwd=repo, check=True,
                   capture_output=True)
    assert _build_plugin().derived_version(repo) == "0.1.90"


def test_setting_the_version_drops_the_compiled_package(tmp_path: Path, monkeypatch) -> None:
    """report-84f1f53a: bytecode compiled in the same second as the version write would keep
    the old version, and test_versions_agree would read it."""
    build = _build_plugin()
    src = tmp_path / "src"
    (src / "__pycache__").mkdir(parents=True)
    (src / "__init__.py").write_text('__version__ = "0.1.1"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('version = "0.1.1"\n', encoding="utf-8")
    stale = src / "__pycache__" / "__init__.cpython-312.pyc"
    stale.write_bytes(b"old")
    monkeypatch.setattr(build, "REPO", tmp_path)
    monkeypatch.setattr(build, "SRC", src)
    build.set_version("0.1.2")
    assert '"0.1.2"' in (src / "__init__.py").read_text(encoding="utf-8")
    assert not stale.exists()
