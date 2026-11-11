"""D3: the driver inside real ``git merge`` and ``git rebase`` (sp6 7.2, 8.1, 8.2)."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pytest

from mergedriver.mdhelpers import (
    commit_all,
    ex,
    install_driver,
    make_repo,
    parse,
    iaso,
    record,
    run_git,
    write_record,
)
from iaso.api import open_core

SR = ".iaso/requirements/SR-005.md"


def _two_sides(tmp_path: Path, **base_fields) -> tuple[Path, Path]:
    root = make_repo(tmp_path / "main")
    install_driver(root)
    write_record(root, record(statement="A relay pins every stated record.",
                              examples=[ex(1)], **base_fields))
    commit_all(root, "SR-005")
    other = tmp_path / "feat"
    run_git(root, "worktree", "add", "-q", "-b", "feat-x", str(other))
    return root, other


@pytest.mark.sr("SR-256")
def test_non_overlapping_changes_merge_clean(tmp_path: Path) -> None:
    root, other = _two_sides(tmp_path)
    write_record(root, record(title="relay checks, scoped",
                              statement="A relay pins every stated record.", examples=[ex(1)]))
    commit_all(root, "title")
    write_record(other, record(statement="A relay pins every stated record.",
                               examples=[ex(1), ex(2, then="two")]))
    commit_all(other, "example")
    merged = run_git(root, "merge", "--no-edit", "feat-x")
    assert "merged field by field" in merged.stderr + merged.stdout
    data, _ = parse((root / SR).read_text(encoding="utf-8"))
    assert data["title"] == "relay checks, scoped"
    assert [e["id"] for e in data["examples"]] == ["EX-1", "EX-2"]
    assert "conflict" not in data
    assert run_git(root, "status", "--porcelain").stdout.strip() == ""


@pytest.mark.sr("SR-256")
def test_content_conflict_becomes_ic(tmp_path: Path) -> None:
    """SR-076 EX-1: both statements kept, labels main and feat-x, unconfirmed, merged."""
    from iaso.approvals import approve

    root, other = _two_sides(tmp_path)
    approve(open_core(root), ["SR-005"])
    commit_all(root, "approved")
    run_git(other, "merge", "-q", "main")
    write_record(root, record(statement="A relay pins only the records the owner affirms.",
                              examples=[ex(1)]))
    commit_all(root, "ours")
    write_record(other, record(statement="A relay pins the stated group, by its title.",
                               examples=[ex(1)]))
    commit_all(other, "theirs")
    merged = run_git(root, "merge", "--no-edit", "feat-x")
    assert "/iaso conflicts" in merged.stderr + merged.stdout
    assert run_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False).returncode
    data, _ = parse((root / SR).read_text(encoding="utf-8"))
    block = data["conflict"]
    assert block["id"] == "IC-001"
    assert (block["ours"]["label"], block["theirs"]["label"]) == ("main", "feat-x")
    assert block["fields"]["statement"]["theirs"].endswith("by its title.")
    core = open_core(root)
    assert core.status(["SR-005"])["SR-005"].confirmation != "confirmed"
    shown = iaso(root, "show", "IC-001")
    assert shown.returncode == 0 and "Conflict IC-001 on \"relay checks\"" in shown.stdout


@pytest.mark.sr("SR-256")
def test_rebase_uses_the_same_driver(tmp_path: Path) -> None:
    root, other = _two_sides(tmp_path)
    write_record(root, record(statement="A relay pins every stated record.",
                              examples=[ex(1), ex(2, then="main")]))
    commit_all(root, "main example")
    write_record(other, record(statement="A relay pins every stated record.",
                               examples=[ex(1), ex(2, then="feat")]))
    commit_all(other, "feat example")
    run_git(other, "rebase", "-q", "main")
    data, _ = parse((other / SR).read_text(encoding="utf-8"))
    assert [(e["id"], e["then"]) for e in data["examples"]] == [
        ("EX-1", "t"), ("EX-2", "main"), ("EX-3", "feat")]


@pytest.mark.sr("SR-256")
def test_driver_under_300_ms(tmp_path: Path) -> None:
    """sp6 7.2: the driver itself (parse, merge, write) stays under 300 ms per file; the
    process start of a cold interpreter is measured separately and only bounded loosely."""
    from iaso.mergedriver import merge_texts

    base = record(statement="a", examples=[ex(i) for i in range(1, 30)])
    ours = record(statement="b", examples=[ex(i) for i in range(1, 31)])
    theirs = record(statement="c", examples=[ex(i) for i in range(1, 30)], domain="x")
    start = time.perf_counter()
    merge_texts(base, ours, theirs, labels=("main", "feat-x"), reserve_ic=lambda: "IC-001")
    assert time.perf_counter() - start < 0.3
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, text in (("b", base), ("o", record(statement="a2")), ("t", base)):
            path = Path(tmp) / name
            path.write_text(text, encoding="utf-8")
            paths.append(str(path))
        best = min(_timed(tmp_path, paths) for _ in range(2))
    assert best < 2.0, best


def _timed(root: Path, paths: list[str]) -> float:
    import subprocess

    start = time.perf_counter()
    subprocess.run([sys.executable, "-m", "iaso", "merge-driver", *paths, SR, "main",
                    "feat-x"], cwd=root, capture_output=True, check=True)
    return time.perf_counter() - start
