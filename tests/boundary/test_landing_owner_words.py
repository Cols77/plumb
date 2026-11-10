"""DEC-116: a landing keeps the owner's words on main when the merged branch stopped tracking
their entries (git deletes a file the other side stopped tracking from the working tree)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.test_log_compaction import put
from mergedriver.mdhelpers import commit_all, run_git
from iaso.boundary import landing
from iaso.log import OWNER_WORDS_KINDS
from understand.fakes import engine_standins  # noqa: F401

pytestmark = pytest.mark.sr("SR-321")


def _tracked(repo: Path) -> dict[str, str]:
    """One owner-words entry per kind, committed on main (as old history has them)."""
    made: dict[str, str] = {}
    for kind in sorted(OWNER_WORDS_KINDS):
        put(repo, kind, {"text": f"my {kind} words"})
        (path,) = (repo / ".iaso" / "log" / kind).glob("*.json")
        run_git(repo, "add", "-f", str(path.relative_to(repo)))
        made[path.relative_to(repo).as_posix()] = path.read_text(encoding="utf-8")
    commit_all(repo, "old history")
    return made


def test_the_landing_restores_the_owners_words_a_merge_deleted(repo: Path) -> None:
    made = _tracked(repo)
    before = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    run_git(repo, "checkout", "-q", "-b", "feat")
    run_git(repo, "rm", "-r", "-q", "--cached", *made)
    commit_all(repo, "stop tracking")
    run_git(repo, "checkout", "-q", "main")
    run_git(repo, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "feat")
    assert not any((repo / name).exists() for name in made), "git deletes them: the premise"
    head = run_git(repo, "rev-parse", "HEAD").stdout.strip()

    result = landing.land(repo, head, before)

    for name, text in made.items():
        assert (repo / name).read_text(encoding="utf-8") == text
    tracked = run_git(repo, "ls-files", ".iaso/log").stdout
    assert not any(name in tracked for name in made)
    assert result["owner_words"] == len(made)
