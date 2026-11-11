"""SR-384: in an adopted repository's main checkout (the primary worktree, on the default
branch) the pre-tool hook refuses an agent's writes: the owner's way is a branch in a worktree,
landed by merge. Only what is listed is refused (shell parsing cannot catch everything; the merge
hold stays behind it), and a failure of the guard allows the call. The owner by hand never goes
through the hook, so nothing here touches them. ``merge.guard_main`` (default true) turns it off."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
REASON = ("iaso: edits in main's checkout are refused; create a branch in a worktree with "
          "git worktree add, and land it by merge.")
IASO_WRITES = frozenset({"capture", "decide", "link", "unlink", "relink", "repin", "proof"})
GIT_WRITES = frozenset({"add", "apply", "rm", "mv", "stash", "cherry-pick", "revert", "rebase"})
PATH_COMMANDS = frozenset({"rm", "mv", "cp", "touch", "mkdir", "chmod", "ln"})
_REDIRECT = re.compile(r"^(?:[0-9]*|&)(>>?)(.*)$")


def _git(directory: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(directory), *args], capture_output=True,
                             text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def main_checkout(directory: Path | str, root: Path | str) -> Path | None:
    """The top of the main checkout ``directory`` is in, or None: not the primary worktree of
    ``root``'s repository, not on its default branch, or ``merge.guard_main`` is false."""
    from iaso.boundary.cli import detected_base, merge_settings
    from iaso.config import load_config

    config = load_config(Path(root))
    if not config.merge.guard_main:
        return None
    directory = Path(directory)
    lines = (_git(directory, "rev-parse", "--show-toplevel", "--git-dir", "--git-common-dir",
                  "--abbrev-ref", "HEAD") or "").splitlines()
    if len(lines) != 4:
        return None
    top = Path(lines[0]).resolve()
    if (directory / lines[1]).resolve() != (directory / lines[2]).resolve():
        return None                                  # a linked worktree
    common = (_git(Path(root), "rev-parse", "--git-common-dir") or "").strip()
    if not common or (Path(root) / common).resolve() != (directory / lines[2]).resolve():
        return None                                  # not the adopted repository
    base = merge_settings(SimpleNamespace(config=config, root=top))["default_base"]
    return top if lines[3] == (base or detected_base(top)) else None


def _counts(top: Path, base: Path, arg: str) -> bool:
    """``arg`` (a path as written, relative to ``base``) is inside the repository ``top`` and
    neither git-ignored nor in a linked worktree nested in it."""
    if not arg or "$" in arg or "`" in arg:
        return False
    path = (base / Path(arg).expanduser()).resolve()
    if not path.is_relative_to(top):
        return False
    near = path
    while not near.exists() and near != top:
        near = near.parent
    near = near if near.is_dir() else near.parent
    inner = (_git(near, "rev-parse", "--show-toplevel") or "").strip()
    if not inner or Path(inner).resolve() != top:
        return False
    return subprocess.run(["git", "-C", str(top), "check-ignore", "-q", str(path)],
                          capture_output=True, timeout=5, check=False).returncode != 0


def _merging(top: Path) -> bool:
    out = (_git(top, "rev-parse", "--git-path", "MERGE_HEAD") or "").strip()
    return bool(out) and (top / out).exists()


def _options_and_args(words: list[str]) -> list[str]:
    return [w for w in words if not w.startswith("-")]


def _targets(name: str, words: list[str]) -> list[str]:
    """The path arguments of a file command that writes to them."""
    args = _options_and_args(words[1:])
    if name == "chmod":
        return args[1:]
    if name in ("cp", "ln"):
        return args[-1:]
    if name == "sed":
        if not any(re.fullmatch(r"-[A-Za-z]*i.*", w) or w == "--in-place" for w in words[1:]):
            return []
        scripted = any(w.startswith("-e") or w.startswith("-f") or w.startswith("--expression")
                       or w.startswith("--file") for w in words[1:])
        return args if scripted else args[1:]
    return args


def _bash_refuses(top: Path, base: Path, words: list[str]) -> bool:
    from iaso.guard import _ASSIGN, _PREFIX_WORDS, _base, iaso_args

    words = list(words)
    for i, word in enumerate(words):                 # a redirect, wherever it stands
        match = _REDIRECT.match(word)
        if match:
            target = match.group(2) or (words[i + 1] if i + 1 < len(words) else "")
            if target and not target.startswith("&") and target != "/dev/null" \
                    and _counts(top, base, target):
                return True
    while words[:1] == ["rtk"] or (words and (_ASSIGN.match(words[0])
                                              or words[0] in _PREFIX_WORDS)):
        words = words[2:] if words[:2] == ["rtk", "bypass"] else words[1:]
    if not words:
        return False
    args = iaso_args(words)
    if args is not None:
        sub = next((a for a in args if not a.startswith("-")), "")
        return sub in IASO_WRITES or (
            sub == "intent" and any(a == "--quote" or a.startswith("--quote=") for a in args))
    name = _base(words[0]).lower()
    if name in PATH_COMMANDS or name in ("sed", "tee"):
        return any(_counts(top, base, t) for t in _targets(name, words))
    if name != "git":
        return False
    rest = words[1:]
    while rest and rest[0].startswith("-"):          # git -C dir / -c k=v ahead of the verb
        if rest[0] == "-C" and len(rest) > 1:
            base = (base / rest[1]).resolve()
        rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
    if not rest or not _counts_dir(base, top):
        return False
    sub, flags = rest[0], rest[1:]
    if sub == "commit":
        return not _merging(top)
    if sub == "reset":
        return "--hard" in flags
    if sub in ("add", "rm", "mv", "apply"):          # resolving a merge stages files
        return not (sub != "apply" and _merging(top))
    if sub in ("cherry-pick", "revert", "rebase"):
        return not {"--abort", "--quit"} & set(flags)
    if sub == "stash":
        return not (flags[:1] and flags[0] in ("list", "show"))
    return False


def _counts_dir(directory: Path, top: Path) -> bool:
    inner = (_git(directory, "rev-parse", "--show-toplevel") or "").strip()
    return bool(inner) and Path(inner).resolve() == top


def _bash(root: Path, command: str, cwd: Path) -> bool:
    from iaso.guard import commands

    top: Path | None = None
    known: dict[Path, Path | None] = {}
    base = cwd
    for words in commands(command):
        if words[0] in ("cd", "pushd") and len(words) > 1 and not words[1].startswith("-"):
            base = (base / Path(words[1]).expanduser()).resolve()
            continue
        if base not in known:
            known[base] = main_checkout(base, root)
        top = known[base]
        if top is not None and _bash_refuses(top, base, words):
            return True
    return False


def refusal(root: Path | str, tool: str, tool_input: dict[str, Any],
            data: dict[str, Any] | None = None) -> str:
    """The refusal text for an agent's call in main's checkout, else "". Never raises."""
    if os.environ.get("IASO_JOB"):      # iaso's own job session: hooks leave it alone
        return ""
    try:
        root = Path(root).resolve()
        cwd = root / str((data or {}).get("cwd") or ".")
        if tool == "Bash":
            return REASON if _bash(root, str(tool_input.get("command") or ""), cwd) else ""
        if tool in EDIT_TOOLS:
            raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
            near = (cwd / Path(raw).expanduser()).resolve().parent   # the file's checkout decides,
            while not near.exists() and near != near.parent:        # not where the session sits
                near = near.parent
            top = main_checkout(near, root)
            return REASON if top is not None and _counts(top, cwd, raw) else ""
    except Exception:  # noqa: BLE001 - a hook never blocks on its own failure
        pass
    return ""
