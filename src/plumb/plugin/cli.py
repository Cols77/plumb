"""``plumb plugin ignore|unignore|migrate`` (SP7 4.5, 4.7; SR-083, SR-084).

- ``ignore`` ("don't use plumb here") adds the repository to ``PLUMB_HOME/ignored``: the
  plugin's hooks then stay silent there, the one adoption line included. ``unignore`` ("use
  plumb here again") removes it.
- ``migrate`` ("move plumb to the plugin") removes exactly what plumb's per-repository
  installer wrote: its entries in ``.claude/settings.json``, the copies of the command, the
  skills and the gate script that still equal a rendering of their template, the ``CLAUDE.md``
  block; it points git's checks and the record merge driver at the user-level launcher, and
  names what it kept (an edited copy, the owner's own settings).

The answers are plain words (R14): the owner never reads a path list."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from plumb.cliutil import add_common, resolve_root


def _forms(root: Path) -> list[str]:
    """The spellings of ``root`` the hooks' shell may compare (``C:/x`` and ``/c/x`` on
    Windows)."""
    text = str(Path(root).resolve()).replace("\\", "/")
    forms = [text]
    if len(text) > 2 and text[1] == ":":
        forms.append("/" + text[0].lower() + text[2:])
    return forms


def ignored_path() -> Path:
    from plumb.launcher import plumb_home

    return plumb_home() / "ignored"


def _ignored_lines() -> list[str]:
    try:
        return [line for line in ignored_path().read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except OSError:
        return []


def ignore(root: Path) -> None:
    lines = _ignored_lines()
    lines += [form for form in _forms(root) if form not in lines]
    path = ignored_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def unignore(root: Path) -> None:
    forms = set(_forms(root))
    lines = [line for line in _ignored_lines() if line not in forms]
    path = ignored_path()
    if path.exists():
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8",
                        newline="\n")


def is_ignored(root: Path) -> bool:
    lines = set(_ignored_lines())
    return any(form in lines for form in _forms(root))


# --------------------------------------------------------------------------- migrate


def _digest(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def known_digests() -> set[str]:
    try:
        data = json.loads((Path(__file__).parent / "known_templates.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(d) for d in data.get("digests") or ()}


def _renderings(root: Path, name: str) -> set[str]:
    from plumb.hosts.claude_code import install

    launchers = [install.Launcher("path", "plumb", "plumb"),
                 install.Launcher("uv", "uv run --no-sync plumb", "uv run --no-sync plumb"),
                 install.Launcher("uv", "uv run plumb", "uv run plumb")]
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        launchers.append(install.Launcher("venv", "", f"{rel} -m plumb"))
    return {_digest(install.template(name, launcher)) for launcher in launchers}


def _copies(root: Path) -> list[tuple[Path, str, str]]:
    """``(path, template name, what the owner calls it)`` of each file the installer copies."""
    from plumb.hosts.claude_code import install

    claude = root / ".claude"
    out = [(claude / "commands" / "plumb.md", "plumb-command.md", "the /plumb command")]
    for name in install.skill_files():             # each skill's SKILL.md and its references
        skill = name.split("/")[1]
        out.append((claude / name, name, f"the {skill} skill"))
    out.append((root / install.GATE_SCRIPT, "gate.sh", "plumb's edit check"))
    return out


def _prune(path: Path, stop: Path) -> None:
    """Remove empty folders from ``path`` up to (not including) ``stop``."""
    current = path
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def migrate(root: Path) -> tuple[bool, list[str]]:
    """``(was set up the old way, owner lines)``; idempotent."""
    from plumb.hosts.claude_code import install
    from plumb.present import owner_text

    root = Path(root)
    kept: list[str] = []
    found = False
    settings_path = root / ".claude" / "settings.json"
    if settings_path.exists():
        settings = install.read_settings(root)
        cleaned = install.unmerge_settings(settings)
        if cleaned != settings:
            found = True
            if cleaned:
                settings_path.write_text(install._dump(cleaned), encoding="utf-8",
                                         newline="\n")
            else:
                settings_path.unlink()
                _prune(settings_path.parent, root)
        if cleaned:
            kept.append(owner_text.MIGRATE_KEPT_SETTINGS)
    known = known_digests()
    for path, name, what in _copies(root):
        if not path.exists():
            continue
        found = True
        digest = _digest(path.read_text(encoding="utf-8", errors="replace"))
        if digest in known or digest in _renderings(root, name):
            path.unlink()
            _prune(path.parent, root)
        elif owner_text.MIGRATE_KEPT.format(what=what) not in kept:
            kept.append(owner_text.MIGRATE_KEPT.format(what=what))
    for folder in install.retired_skills(root):    # the skill under its retired name (DEC-036)
        found = True
        (folder / "SKILL.md").unlink()
        _prune(folder, root)
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        stripped = install.without_block(text)
        if stripped != text:
            found = True
            if stripped.strip():
                claude_md.write_text(stripped, encoding="utf-8", newline="\n")
            else:
                claude_md.unlink()
    if not found:
        return False, [owner_text.MIGRATE_NOTHING]
    git_lines: list[str] = []
    if (root / ".git").exists():
        install.commit_msg_adoption(root, sys.executable, git_lines)
        install.git_adoption(root, sys.executable, git_lines, False)
    kept += [line for line in git_lines if "was kept" in line or "not installed" in line]
    return True, [owner_text.MIGRATE_DONE, *kept]


# --------------------------------------------------------------------------- command


def run(command: str, argv: list[str]) -> int:
    from plumb.present import owner_text

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="plumb as a Claude Code plugin: ignore (stay out of this repository), "
                    "unignore, migrate (from the per-repository install).")
    add_common(parser)
    parser.add_argument("action", choices=("ignore", "unignore", "migrate"))
    args = parser.parse_args(argv)
    root = resolve_root(args.root or os.environ.get("CLAUDE_PROJECT_DIR") or None)
    if args.action == "ignore":
        ignore(root)
        print(owner_text.IGNORED)
        return 0
    if args.action == "unignore":
        unignore(root)
        print(owner_text.UNIGNORED)
        return 0
    _, lines = migrate(root)
    print("\n".join(lines))
    return 0
