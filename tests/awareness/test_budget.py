"""A5: awareness stays cheap: 50 ms warm for five worktrees, no git process on the prompt
path, a spent budget skips quietly (SR-079)."""

from __future__ import annotations

import statistics
import subprocess
import time
from pathlib import Path

import pytest

from awareness.gitrepo import add_worktree, commit_all, make_repo, requirement
from plumb import awareness
from plumb.api import open_core
from plumb.awareness import publish as pub

pytestmark = pytest.mark.sr("SR-258")


def _five(tmp_path: Path) -> Path:
    main = make_repo(tmp_path / "main")
    for i in range(1, 31):
        requirement(main, f"SR-{i:03d}", f"thing {i}")
    commit_all(main, "records")
    for n in range(5):
        other = add_worktree(main, tmp_path / f"wt-{n}", f"feat-{n}")
        paths = []
        for i in range(n * 3 + 1, n * 3 + 4):
            requirement(other, f"SR-{i:03d}", f"thing {i}", f"feat-{n} version")
            paths.append(f".plumb/requirements/SR-{i:03d}.md")
        pub.publish(open_core(other), paths)
    return main


def test_five_worktrees_under_50_ms_warm_no_git_process(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch
                                                        ) -> None:
    """SR-079 EX-1: the prompt hook's overlap check, warm caches."""
    main = _five(tmp_path)
    core = open_core(main)
    core.index()
    awareness.delta_lines(core, ["SR-001"])          # warm: the register and file caches

    def refuse(*a: object, **k: object) -> None:
        raise AssertionError("a git process was started on the prompt path")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    ids = ["SR-001", "SR-004", "SR-007", "SR-010", "SR-013"]
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        lines = awareness.delta_lines(core, ids)
        runs.append((time.perf_counter() - start) * 1000)
    assert len(lines) == 5
    assert statistics.median(runs) < 50, runs


def test_budget_exhausted_skips_quietly(tmp_path: Path) -> None:
    main = _five(tmp_path)

    class Spent:
        def expired(self) -> bool:
            return True

        def remaining_s(self) -> float:
            return 0.0

    assert awareness.overlaps(open_core(main), ["SR-001"], deadline=Spent()) == ()
    errors = (main / ".plumb" / "session" / "errors.log").read_text(encoding="utf-8")
    assert "plumb: awareness skipped (budget)" in errors
