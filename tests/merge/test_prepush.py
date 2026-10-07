"""M6: the optional git ``pre-push`` hook (sp3 8, SR-051)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from merge_helpers import commit, git, write

from plumb import cli
from plumb.boundary import install_pre_push_hook
from plumb.boundary.prepush import HOOK_MARKER, ForeignHookError, uninstall_pre_push_hook

pytestmark = pytest.mark.sr("SR-051")

FOREIGN = "#!/bin/sh\necho foreign\n"


def _hook(root: Path) -> Path:
    return root / ".git" / "hooks" / "pre-push"


def test_installs_and_leaves_foreign_hook(repo: Path, capsys) -> None:
    """SR-051 EX-1: a foreign pre-push hook is unchanged and reported."""
    _hook(repo).parent.mkdir(parents=True, exist_ok=True)
    _hook(repo).write_text(FOREIGN, encoding="utf-8")
    with pytest.raises(ForeignHookError):
        install_pre_push_hook(repo, sys.executable)
    assert cli.main(["merge-check", "--install-pre-push", "--root", str(repo)]) == 1
    assert "foreign pre-push hook" in capsys.readouterr().err
    assert _hook(repo).read_text(encoding="utf-8") == FOREIGN
    _hook(repo).unlink()
    assert cli.main(["merge-check", "--install-pre-push", "--root", str(repo)]) == 0
    text = _hook(repo).read_text(encoding="utf-8")
    assert HOOK_MARKER in text and "-m plumb merge-check --hook pre-push" in text
    assert install_pre_push_hook(repo, sys.executable) == _hook(repo)  # idempotent


def test_uninstall_removes_only_plumb_hook(repo: Path, capsys) -> None:
    _hook(repo).parent.mkdir(parents=True, exist_ok=True)
    _hook(repo).write_text(FOREIGN, encoding="utf-8")
    assert uninstall_pre_push_hook(repo) is False
    assert cli.main(["merge-check", "--uninstall-pre-push", "--root", str(repo)]) == 0
    assert _hook(repo).read_text(encoding="utf-8") == FOREIGN
    _hook(repo).unlink()
    install_pre_push_hook(repo, sys.executable)
    assert uninstall_pre_push_hook(repo) is True
    assert not _hook(repo).exists()


def test_hooks_install_installs_pre_push(repo: Path) -> None:
    """R17: the merge-time check runs no tests because the one full run happens at push, so
    hooks install writes the pre-push hook by default."""
    assert cli.main(["hooks", "install", "--root", str(repo), "--launcher", "uv"]) == 0
    assert (repo / ".git" / "hooks" / "commit-msg").exists()
    assert HOOK_MARKER in _hook(repo).read_text(encoding="utf-8")


def test_hook_blocks_push_on_nonzero(repo: Path, tmp_path: Path) -> None:
    """SR-051 EX-2: a branch whose report exits 4 cannot be pushed through the hook."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    install_pre_push_hook(repo, sys.executable)
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, ".plumb/requirements/SR-001.md",
          "---\nid: SR-001\ntitle: New\nstatement: A new behaviour.\n---\n")
    commit(repo, "propose SR-001\n\nSR: SR-001")
    pushed = subprocess.run(["git", "push", "origin", "feat"], cwd=repo, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    assert pushed.returncode != 0, pushed.stdout + pushed.stderr
    assert "SR-001" in pushed.stdout + pushed.stderr
    probe = subprocess.run(["git", "ls-remote", str(remote), "refs/heads/feat"],
                           capture_output=True, text=True)
    assert probe.stdout.strip() == ""


def test_hook_mode_reads_refs_and_allows_green(repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    install_pre_push_hook(repo, sys.executable)
    git(repo, "push", "-q", "origin", "main")  # a new branch with nothing touched: green
    write(repo, "notes.md", "n\n")
    commit(repo, "notes")
    pushed = subprocess.run(["git", "push", "origin", "main"], cwd=repo, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    assert pushed.returncode == 0, pushed.stdout + pushed.stderr
