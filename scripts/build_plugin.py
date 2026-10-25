"""Build the Claude Code plugin's GENERATED files and its vendored wheel (SP7 4.1, 4.2).

    python scripts/build_plugin.py            # write every generated file and the wheel
    python scripts/build_plugin.py --check    # exit 1 naming what is stale; writes nothing
    python scripts/build_plugin.py --no-wheel # the text files only (the wheel left as it is)

GENERATED from the one source of each (so the legacy installer and the plugin never drift):

- ``plugin/commands/plumb.md`` and every file of ``plugin/skills/<name>/`` (``SKILL.md`` and
  any reference files beside it): the templates under ``src/plumb/hosts/claude_code/templates``,
  each ``.md`` rendered with ``{plumb}`` as ``plumb`` (the session-start hook puts the plugin's
  ``bin`` on the agent's PATH), any other file as it is; a file or skill folder under
  ``plugin/skills`` with no template (a skill renamed, a reference dropped) is stale, and the
  build removes it;
- ``plugin/bin/gate.sh``: SP8's edit gate, the template as it is;
- ``plugin/hooks/guard.gen.ts``: the guard table of ``plumb.guard`` for the mod (SP7 5.9);
- ``plugin/hooks/hooks.json``: the command hooks and the mod module;
- ``plugin/.claude-plugin/plugin.json`` and ``.claude-plugin/marketplace.json``: the version
  is ``pyproject.toml``'s;
- ``plugin/LICENSE``: the repository's ``LICENSE`` as it is (SR-123), so the two never drift;
- ``plugin/vendor/plumb-<version>-py3-none-any.whl`` and ``plugin/vendor/MANIFEST.json``
  ``{version, wheel, sha256, source_digest}``; ``source_digest`` is the digest of
  ``src/plumb/**`` (templates included) and ``pyproject.toml``.

``--check`` also fails naming any test-only file under ``plugin/`` (``*.test.*``,
``harness.ts``, ``fixtures.ts``): the mod's tests live in ``tests/plugin/mod`` (SR-123), since a
marketplace install copies the whole plugin folder. ``plugin/README.md`` is hand-written.

``tests/plugin/test_bundle_fresh.py`` runs ``--check``."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugin"
SRC = REPO / "src" / "plumb"
TEMPLATES = SRC / "hosts" / "claude_code" / "templates"
HOST_TEMPLATES = TEMPLATES   # the command and gate.sh (the tests move TEMPLATES, not these)
VENDOR = PLUGIN / "vendor"
DESCRIPTION = ("Keep a coding agent's work aligned with what you asked for: your intent, the "
               "requirements and examples it becomes, and the checks that hold the code to them.")
AUTHOR = {"name": "Colin AUBE"}
REPOSITORY = "https://github.com/Cols77/plumb"
DIAGRAM_MARKETPLACE = "diagram-mod"   # where the diagram mod plumb's cards draw with is published

# (Claude Code event, matcher, plumb hook, async, timeout in seconds): SP7 4.3, with SR-111's
# synchronous edit check and SP8's gate on PreToolUse (the guard covers Bash too). The timeout
# bounds the whole command (sh, the launcher, Python's start); plumb's own watchdog cuts each
# hook at 90 s (``hookio.HARD_LIMIT_S`` or ``hooks.hard_limit_s``; the stop hook's read-back
# gets 1 s more), so these only keep a hung process from holding the session (SR-123, SR-181, SR-310).
# post-edit and edit-check share a
# matcher in two groups because only post-edit is async; they write different files under
# ``.plumb/session/<id>/`` (``touched.txt``, ``stale_told.json``). MultiEdit stays: the legacy
# installer (``plumb.hosts.claude_code.install``) and ``plumb.guard`` still name it.
HOOKS: tuple[tuple[str, str | None, str, bool, int], ...] = (
    ("SessionStart", "startup|resume|clear|compact", "session-start", False, 120),
    ("UserPromptSubmit", None, "prompt", False, 120),
    ("PreToolUse", "Bash|Edit|Write|MultiEdit|NotebookEdit", "pre-tool", False, 120),
    ("PostToolUse", "Edit|Write|MultiEdit|NotebookEdit", "post-edit", True, 120),
    ("PostToolUse", "Edit|Write|MultiEdit|NotebookEdit", "edit-check", False, 120),
    ("PostToolUse", "AskUserQuestion", "question-answer", True, 120),
    ("Stop", None, "stop", False, 120),
    ("SubagentStop", None, "subagent-stop", False, 120),
    ("SessionEnd", None, "session-end", False, 120),
)
# test-only files: they belong in tests/plugin/mod, never in the shipped plugin (SR-123)
TEST_ONLY_NAMES = ("harness.ts", "fixtures.ts")
TEST_MARKS = (".test.", ".spec.", "_test.")   # x.test.tsx, x.spec.ts, x_test.ts
# what the engine lays beside a mod it loads from a folder (gitignored): not the plugin's own
ENGINE_TYPES = PLUGIN / ".claude-plugin" / "types"


def version() -> str:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("build_plugin: no version in pyproject.toml")
    return match.group(1)


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def source_digest() -> str:
    """The digest of what the wheel is built from: ``src/plumb/**`` and ``pyproject.toml``."""
    digest = hashlib.sha256()
    files = sorted(p for p in SRC.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                   and p.suffix not in (".pyc", ".pyo"))
    for path in [*files, REPO / "pyproject.toml"]:
        rel = path.relative_to(REPO).as_posix()
        digest.update(rel.encode("utf-8") + b"\0" + _lf(path.read_bytes()) + b"\0")
    return digest.hexdigest()


def _rel(path: Path) -> str:
    """path as the repository names it (as it is when outside the repository)."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _json(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _render(name: str) -> str:
    """The template ``name`` for the plugin: ``{plumb}`` as the agent types it, and the skills'
    files left under ``${CLAUDE_PLUGIN_ROOT}/skills/``. ``install.template`` points them at
    ``.claude/skills/`` for the per-repository install, where they are copied; in the plugin
    they exist only beside it (``plumb plugin migrate`` deletes the .claude copies)."""
    return _render_text((HOST_TEMPLATES / name).read_text(encoding="utf-8"))


def _render_text(text: str) -> str:
    """``text`` as ``install.template`` renders a template: ``{plumb}`` as what the agent types."""
    sys.path.insert(0, str(REPO / "src"))
    from plumb.hosts.claude_code.install import Launcher

    return text.replace("{plumb}", Launcher("path", "plumb", "plumb").agent_prefix)


def skill_names() -> list[str]:
    base = TEMPLATES / "skills"
    return sorted(d.name for d in base.iterdir() if (d / "SKILL.md").is_file())


def skill_files(name: str) -> dict[str, str]:
    """Every file of the skill ``name`` (its POSIX path in the skill's folder) and its content:
    each ``.md`` rendered as ``SKILL.md`` is, any other file as it is."""
    base = TEMPLATES / "skills" / name
    out = {}
    for path in sorted(p for p in base.rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts):
        rel = path.relative_to(base).as_posix()
        text = path.read_text(encoding="utf-8")  # newlines read as LF, as template() does
        out[rel] = _render_text(text) if path.suffix == ".md" else text
    return out


def hooks_json() -> str:
    hooks: dict[str, list[dict[str, object]]] = {}
    for event, matcher, name, is_async, timeout in HOOKS:
        hook: dict[str, object] = {"type": "command",
                                   "command": f'sh "${{CLAUDE_PLUGIN_ROOT}}/bin/plumb-hook" {name}',
                                   "timeout": timeout}
        if is_async:
            hook["async"] = True
        group: dict[str, object] = {"matcher": matcher} if matcher else {}
        group["hooks"] = [hook]
        hooks.setdefault(event, []).append(group)
    return _json({"description": "plumb's background checks (SP7 4.3) and its in-app panel",
                  "modules": ["./register.tsx"], "hooks": hooks})


def guard_ts() -> str:
    sys.path.insert(0, str(REPO / "src"))
    from plumb import guard

    return ("// GENERATED by scripts/build_plugin.py from plumb.guard.TABLE (SP7 5.9); "
            "do not edit.\n"
            "// The mod's tool.call hook denies the same forms as the pre-tool command hook.\n"
            f"export const MARKER_NAME = {json.dumps(guard.MARKER_NAME)};\n"
            f"export const PROOF = {json.dumps(guard.PROOF)};\n"
            "export type GuardRow = { words: string[]; firstOf: string[]; "
            "unless: string | null; legacy: boolean; why: string };\n"
            "export const GUARD_TABLE: GuardRow[] = "
            + json.dumps(guard.table_data(), indent=2, ensure_ascii=False) + ";\n")


def plugin_json() -> str:
    return _json({"name": "plumb", "version": version(), "description": DESCRIPTION,
                  "author": AUTHOR, "license": "MIT",
                  # SR-358: the repository every install compares its build with
                  "repository": REPOSITORY,
                  "keywords": ["intent", "requirements", "alignment", "tests"],
                  # the mod's $.state contract (SP7 5.6), which `claude plugin validate` checks
                  "types": "./types/index.d.ts",
                  # the card's diagram is drawn by the diagram mod's noun (INT-041, DEC-047);
                  # it lives in its own marketplace, so the dependency names it
                  "dependencies": [f"diagram@{DIAGRAM_MARKETPLACE}"]})


def marketplace_json() -> str:
    return _json({"name": "plumb", "owner": AUTHOR,
                  "description": "plumb, as a Claude Code plugin",
                  # without it Claude Code refuses to install a dependency from another marketplace
                  "allowCrossMarketplaceDependenciesOn": [DIAGRAM_MARKETPLACE],
                  "plugins": [{"name": "plumb", "source": "./plugin", "version": version(),
                               "description": DESCRIPTION, "author": AUTHOR}]})


def text_files() -> dict[Path, str]:
    """Every GENERATED text file and its content."""
    out = {PLUGIN / "commands" / "plumb.md": _render("plumb-command.md"),
           PLUGIN / "bin" / "gate.sh": _render("gate.sh"),
           PLUGIN / "hooks" / "guard.gen.ts": guard_ts(),
           PLUGIN / "hooks" / "hooks.json": hooks_json(),
           PLUGIN / ".claude-plugin" / "plugin.json": plugin_json(),
           REPO / ".claude-plugin" / "marketplace.json": marketplace_json(),
           PLUGIN / "LICENSE": _lf((REPO / "LICENSE").read_bytes()).decode("utf-8")}
    for name in skill_names():
        for rel, content in skill_files(name).items():
            out[PLUGIN / "skills" / name / rel] = content
    return out


def orphans(expected: dict[Path, str]) -> list[Path]:
    """Files under ``plugin/skills`` that no template makes any more (a renamed skill's old
    folder, a dropped reference), deepest first."""
    base = PLUGIN / "skills"
    if not base.is_dir():
        return []
    return sorted((p for p in base.rglob("*") if p.is_file() and p not in expected),
                  key=lambda p: (-len(p.parts), p.as_posix()))


def remove_orphans(expected: dict[Path, str]) -> None:
    """Delete what orphans names, and each folder that leaves empty."""
    base = PLUGIN / "skills"
    for path in orphans(expected):  # deepest first, so a folder it empties goes too
        path.unlink()
        for folder in path.parents:
            if folder == base or any(folder.iterdir()):
                break
            folder.rmdir()


def test_only_files() -> list[Path]:
    """Test-only files under ``plugin/``: the mod's tests live in ``tests/plugin/mod``."""
    return sorted(p for p in PLUGIN.rglob("*") if p.is_file()
                  and (any(mark in p.name for mark in TEST_MARKS)
                       or p.name in TEST_ONLY_NAMES)
                  and ENGINE_TYPES not in p.parents)


def wheel_name() -> str:
    return f"plumb-{version()}-py3-none-any.whl"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest() -> dict[str, str]:
    try:
        return json.loads((VENDOR / "MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def stale() -> list[str]:
    """What no longer matches its source (relative paths, with why)."""
    out = []
    expected = text_files()
    for path, content in expected.items():
        try:
            current = _lf(path.read_bytes()).decode("utf-8")
        except OSError:
            current = None
        if current != content:
            out.append(f"{_rel(path)}: differs from its source")
    for path in orphans(expected):
        out.append(f"{_rel(path)}: no template makes it (remove it)")
    for path in test_only_files():
        out.append(f"{_rel(path)}: a test-only file in the plugin (it belongs in tests/plugin/mod)")
    found = manifest()
    wheel = VENDOR / wheel_name()
    if found.get("version") != version() or found.get("wheel") != wheel_name():
        out.append("plugin/vendor/MANIFEST.json: names another version")
    elif not wheel.is_file() or _sha256(wheel) != found.get("sha256"):
        out.append(f"plugin/vendor/{wheel_name()}: missing or not the one MANIFEST.json names")
    if found.get("source_digest") != source_digest():
        out.append("plugin/vendor: the wheel was built from another source (rebuild it)")
    return out


def build_wheel() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["uv", "build", "--wheel", "--out-dir", tmp, str(REPO)], check=True,
                       cwd=REPO)
        built = Path(tmp) / wheel_name()
        if not built.is_file():
            raise SystemExit(f"build_plugin: uv build did not produce {wheel_name()}")
        for old in VENDOR.glob("plumb-*.whl"):
            old.unlink()
        shutil.copyfile(built, VENDOR / wheel_name())
    data = {"version": version(), "wheel": wheel_name(),
            "sha256": _sha256(VENDOR / wheel_name()), "source_digest": source_digest()}
    (VENDOR / "MANIFEST.json").write_text(_json(data), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="name what is stale; write nothing")
    parser.add_argument("--no-wheel", action="store_true", help="leave the wheel as it is")
    args = parser.parse_args(argv)
    if args.check:
        found = stale()
        for line in found:
            print(line)
        return 1 if found else 0
    expected = text_files()
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    remove_orphans(expected)
    for path in test_only_files():  # never deleted: they are someone's tests; --check names them
        print(f"build_plugin: {_rel(path)} is test-only; move it to tests/plugin/mod",
              file=sys.stderr)
    if not args.no_wheel:
        build_wheel()
    print("plugin built" + ("" if args.no_wheel else f": {wheel_name()}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
