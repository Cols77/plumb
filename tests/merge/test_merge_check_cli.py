"""M5: ``plumb merge-check [BASE] [--no-run] [--json]``: one screen, capped lists, and no
writes but the merge evidence (sp3 7, SR-052)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from merge_helpers import commit, git, project, write

from plumb import approvals, cli
from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-260")


def _snapshot(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        # .plumb/cache/ and the gitignored derived map are caches: rebuilt, never state
        if not path.is_file() or rel.startswith((".git/", ".plumb/cache/")) \
                or rel == ".plumb/test_map.txt":
            continue
        if "__pycache__" in rel or ".pytest_cache" in rel:
            continue
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def test_report_caps_lists(repo: Path, capsys) -> None:
    """SR-052 EX-2: 25 untraced paths show 10 and the rest in --json."""
    base = _head(repo)
    for n in range(25):
        write(repo, f"src/m{n:02d}.py", "x = 1\n")
    assert cli.main(["merge-check", base, "--no-run", "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    shown = [line for line in out.splitlines() if line.startswith("  untraced src/m")]
    assert len(shown) == 10
    assert "+15 more (plumb merge-check --json)" in out
    assert cli.main(["merge-check", base, "--no-run", "--json", "--root", str(repo)]) == 0
    assert len(json.loads(capsys.readouterr().out)["untraced"]) == 25


def _head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").strip()


def test_writes_nothing_but_merge_evidence(repo: Path, capsys) -> None:
    """SR-052 EX-1: --no-run changes no file outside .plumb/cache."""
    project(repo)
    sha = commit(repo, "project")
    write(repo, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    before = _snapshot(repo)
    code = cli.main(["merge-check", sha, "--no-run", "--root", str(repo)])
    assert code in (0, 1, 4, 5)
    assert _snapshot(repo) == before
    out = capsys.readouterr().out
    assert len([line for line in out.splitlines() if not line.startswith("  ")]) <= 20


def test_default_base_and_green_exit(repo: Path, capsys) -> None:
    project(repo)
    approvals.approve(open_core(repo), ["SR-001", "SR-002", "INT-001"])
    commit(repo, "project")
    git(repo, "checkout", "-q", "-b", "feat")
    code = cli.main(["merge-check", "--root", str(repo)])  # BASE defaults to main
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.startswith("plumb merge-check: main..HEAD")
    assert "full run:" in out and "merge evidence: recorded" in out


def test_usage_errors(repo: Path, capsys) -> None:
    assert cli.main(["merge-check", "no-such-ref", "--no-run", "--root", str(repo)]) == 2
    assert "cannot read the range" in capsys.readouterr().out
    assert cli.main(["merge-check", "--bogus", "--root", str(repo)]) == 2


def test_merge_wait_line_is_counted_with_no_id(repo: Path) -> None:
    from plumb.boundary import merge_report, render

    base = _head(repo)
    for n in range(1, 13):
        write(repo, f".plumb/requirements/SR-{n:03d}.md",
              f"---\nid: SR-{n:03d}\ntitle: R{n}\nstatement: s{n}.\n---\n")
    report = merge_report(open_core(repo), base, run_full=False)
    assert len(report.awaiting) == 12 and report.exit == 0          # listed (SR-260 EX-31)
    line = next(x for x in render(report) if x.startswith("plumb: waiting on a judge"))
    assert line.startswith("plumb: waiting on a judge: 12 records")              # counted
    assert "SR-0" not in line and "plumb approve" not in line                     # SR-267
