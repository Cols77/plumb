"""The optional git ``pre-push`` hook (sp3 8, SR-051).

``plumb merge-check --install-pre-push`` writes ``pre-push`` in the shared hooks directory
(``git rev-parse --git-path hooks/pre-push``, which honours ``core.hooksPath`` and is shared by
every worktree), running ``<interpreter> -m plumb merge-check --hook pre-push``. A hook plumb
did not write is left untouched and reported. ``plumb hooks install`` never installs it; the
owner (or the agent on the owner's request) does. ``git push --no-verify`` bypasses it, like
any git hook: tamper-evident, not tamper-proof.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

HOOK_MARKER = "# plumb pre-push hook"
ZERO = "0" * 40


class ForeignHookError(RuntimeError):
    """A ``pre-push`` hook plumb did not write exists; it is left untouched."""


def hook_path(root: Path) -> Path:
    out = subprocess.run(["git", "rev-parse", "--git-path", "hooks/pre-push"], cwd=root,
                         capture_output=True, text=True, check=True, encoding="utf-8")
    path = Path(out.stdout.strip())
    return path if path.is_absolute() else Path(root) / path


def hook_text(interpreter: str) -> str:
    exe = interpreter.replace("\\", "/")
    return (f"#!/bin/sh\n{HOOK_MARKER} (written by `plumb merge-check --install-pre-push`)\n"
            f'exec "{exe}" -m plumb merge-check --hook pre-push\n')


def _is_plumb(path: Path) -> bool:
    try:
        return HOOK_MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ForeignHookError(f"cannot read the existing hook {path}: {exc}") from exc


def install_pre_push_hook(root: Path, interpreter: str) -> Path:
    """Write plumb's pre-push hook (idempotent); a foreign hook raises ``ForeignHookError``."""
    path = hook_path(Path(root))
    if path.exists() and not _is_plumb(path):
        raise ForeignHookError(f"a foreign pre-push hook exists at {path}; left untouched "
                               "(call `plumb merge-check --hook pre-push` from it)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hook_text(interpreter).encode("utf-8"))
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path


def uninstall_pre_push_hook(root: Path) -> bool:
    """Remove plumb's pre-push hook; returns False (and leaves it) when it is foreign or
    absent."""
    path = hook_path(Path(root))
    if not path.exists() or not _is_plumb(path):
        return False
    path.unlink()
    return True


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else None


def hook_bases(root: Path, lines: Iterable[str], default_base: str) -> list[tuple[str, str]]:
    """``[(local ref, base)]`` for the pushed refs that point at the checked-out HEAD.

    git gives ``<local ref> <local sha> <remote ref> <remote sha>`` per line. The base is the
    remote sha when this repository knows it, else (a new branch, or a remote ahead) the
    merge base of HEAD with ``default_base``. A deleted ref, or a ref that is not HEAD (the
    report covers the working tree only), is skipped."""
    head = _git(root, "rev-parse", "HEAD")
    out: list[tuple[str, str]] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        local_ref, local_sha, _remote_ref, remote_sha = parts[:4]
        if local_sha == ZERO or local_sha != head:
            continue
        base = None
        if remote_sha != ZERO and _git(root, "cat-file", "-e", f"{remote_sha}^{{commit}}") \
                is not None:
            base = remote_sha
        elif _git(root, "rev-parse", "--verify", "--quiet", default_base) is not None:
            base = _git(root, "merge-base", default_base, "HEAD")
        if base:
            out.append((local_ref, base))
    return out
