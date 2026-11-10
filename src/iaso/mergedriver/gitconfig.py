"""The record merge driver's installation (sp6 7.1, SR-075).

- ``.iaso/.gitattributes`` gains ``<dir>/*.md merge=iaso-record`` for each record
  directory, once each; other lines are kept. The file is committed, so every clone shares
  the attribute.
- The repository's git config (shared by every worktree of the clone) gains
  ``merge.iaso-record.name`` and ``merge.iaso-record.driver = <launcher> merge-driver
  %O %A %B %P %X %Y``, where ``<launcher>`` is the one the commit-msg hook uses.

A clone where the driver is not configured falls back to git's text merge for record files
(the attribute names an unknown driver). ``uninstall`` removes exactly these lines and keys.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from iaso.present import owner_text

DRIVER = "iaso-record"
RECORD_DIRS = ("intents", "requirements", "decisions", "features", "ncs")
ATTR_LINES = tuple(f"{d}/*.md merge={DRIVER}" for d in RECORD_DIRS)
NAME = "iaso record merge"
KEYS = (f"merge.{DRIVER}.name", f"merge.{DRIVER}.driver")


def driver_command(launcher: str) -> str:
    return f"{launcher} merge-driver %O %A %B %P %X %Y"


def launcher_for(interpreter: str) -> str:
    """The launcher of the record merge driver: ``"<interpreter>" -m iaso``, or the user-level
    launcher under the plugin (``iaso.launcher``, SP7 4.6)."""
    from iaso import launcher

    return launcher.driver_command(interpreter)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30)


def _in_git(root: Path) -> bool:
    try:
        return _git(root, "rev-parse", "--git-dir").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _attr_path(root: Path) -> Path:
    return Path(root) / ".iaso" / ".gitattributes"


def _attr_lines(root: Path) -> list[str]:
    try:
        return _attr_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _config(root: Path, key: str) -> str | None:
    out = _git(root, "config", "--get", key)
    return out.stdout.strip() if out.returncode == 0 else None


def install(root: Path, launcher: str, *, dry_run: bool = False) -> list[str]:
    """Declare the driver (idempotent). Returns one line per change, or "unchanged"."""
    root = Path(root)
    lines: list[str] = []
    current = _attr_lines(root)
    present = {line.strip() for line in current}
    missing = [line for line in ATTR_LINES if line not in present]
    if missing:
        if not dry_run:
            path = _attr_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            text = "\n".join(current)
            text = (text + "\n" if text else "") + "\n".join(missing) + "\n"
            path.write_text(text, encoding="utf-8", newline="\n")
        lines.append(("iaso: would write" if dry_run else "iaso: wrote")
                     + " .iaso/.gitattributes (record files merge field by field)")
    if not _in_git(root):
        lines.append("iaso: not a git repository; the record merge driver is not configured")
        return lines
    wanted = {KEYS[0]: NAME, KEYS[1]: driver_command(launcher)}
    changed = [key for key, value in wanted.items() if _config(root, key) != value]
    if changed and not dry_run:
        for key in changed:
            _git(root, "config", key, wanted[key])
    if changed:
        lines.append(("iaso: would configure" if dry_run else "iaso: configured")
                     + f" the record merge driver (git config merge.{DRIVER})")
    if not lines:
        lines.append("iaso: record merge driver unchanged")
    return lines


def uninstall(root: Path, *, dry_run: bool = False) -> list[str]:
    """Remove exactly iaso's attribute lines and git config keys."""
    root = Path(root)
    lines: list[str] = []
    current = _attr_lines(root)
    kept = [line for line in current if line.strip() not in ATTR_LINES]
    if kept != current:
        if not dry_run:
            path = _attr_path(root)
            if any(line.strip() for line in kept):
                path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
            else:
                path.unlink()
        lines.append(("iaso: would remove" if dry_run else "iaso: removed")
                     + " the record merge lines of .iaso/.gitattributes")
    if _in_git(root):
        present = [key for key in KEYS if _config(root, key) is not None]
        if present and not dry_run:
            for key in present:
                _git(root, "config", "--unset-all", key)
            if _git(root, "config", "--get-regexp", rf"^merge\.{DRIVER}\.").returncode != 0:
                _git(root, "config", "--remove-section", f"merge.{DRIVER}")
        if present:
            lines.append(("iaso: would remove" if dry_run else "iaso: removed")
                         + " the record merge driver from git config")
    return lines


def status(root: Path) -> str:
    """``merge driver: installed | not installed | attribute without driver``, the last two
    followed by how to install it (``owner_text.DRIVER_STATUS``)."""
    root = Path(root)
    has_attr = all(line in {x.strip() for x in _attr_lines(root)} for line in ATTR_LINES)
    has_driver = _in_git(root) and bool(_config(root, KEYS[1]))
    if has_attr and has_driver:
        return owner_text.DRIVER_STATUS.format(state=owner_text.DRIVER_INSTALLED)
    state = owner_text.DRIVER_HALF if has_attr else owner_text.DRIVER_NOT_INSTALLED
    return owner_text.DRIVER_STATUS.format(state=state) + owner_text.DRIVER_MISSING
