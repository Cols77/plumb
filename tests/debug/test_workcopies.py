"""INT-125: debug work copies are made without the committed log (SR-400), idle ones are
removed at a landing and by plumb debug prune (SR-401), and a new one is refused when the
disk is nearly full (SR-402). Git is real; the free space is stubbed."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from boundary.test_landing import docs, head, land_branch
from core.test_log_compaction import put
from mergedriver.mdhelpers import commit_all, run_git
from plumb import cli, debug, selfdebug
from plumb.boundary import landing

LOW = SimpleNamespace(total=100 * 10**9, used=98 * 10**9, free=2 * 10**9)
HIGH = SimpleNamespace(total=100 * 10**9, used=50 * 10**9, free=50 * 10**9)


@pytest.fixture(autouse=True)
def room(monkeypatch: pytest.MonkeyPatch) -> None:
    """The disk the tests run on may itself be short; a test that wants it short says so."""
    monkeypatch.setattr(shutil, "disk_usage", lambda p: HIGH)
    monkeypatch.setattr(selfdebug, "FLOOR_GB", 5)


@pytest.fixture
def main(repo: Path) -> Path:
    """A repository whose tracked log holds entry files, ready to make work copies from."""
    for n in range(30):
        put(repo, "test-run", {"n": n})
    commit_all(repo, "log")
    return repo


def copy(root: Path, case: str) -> Path:
    return selfdebug._worktree(root, case)[0]


def log_files(tree: Path) -> list[Path]:
    return list((tree / ".plumb" / "log").glob("**/*.json"))


def dirty(tree: Path) -> str:
    return run_git(tree, "status", "--porcelain").stdout


@pytest.mark.sr("SR-400")
def test_sr400_ex1_a_work_copy_has_the_code_and_records_but_no_log_entry_files(main: Path) -> None:
    tree = copy(main, "case-a")
    assert (tree / "README.md").exists() and (tree / ".plumb" / "config.yaml").exists()
    assert log_files(main) and log_files(tree) == [] and dirty(tree) == ""


@pytest.mark.sr("SR-400")
def test_sr400_ex2_plumb_runs_in_a_work_copy_with_a_cache_of_its_own(main: Path) -> None:
    tree = copy(main, "case-a")
    done = subprocess.run([sys.executable, "-m", "plumb", "status", "--root", str(tree)],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")})
    assert done.returncode in (0, 1), done.stderr
    cache = tree / ".plumb" / "cache"
    assert cache.is_dir() and not cache.is_symlink()
    assert sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) < 1_000_000


@pytest.mark.sr("SR-400")
def test_sr400_ex3_a_copy_made_before_the_rule_is_reused_as_it_is(main: Path) -> None:
    old = main / ".plumb" / "wt" / "debug-case-a"
    run_git(main, "worktree", "add", "-q", "-b", "debug/case-a", str(old))
    assert log_files(old)
    assert copy(main, "case-a") == old and log_files(old)


@pytest.mark.sr("SR-401")
def test_sr401_ex1_a_landing_removes_an_idle_copy_and_names_it(main: Path) -> None:
    tree = copy(main, "case-a")
    sha, before = land_branch(main, lambda r: docs(r, "x.md"))
    line = landing.land(main, sha, before)
    assert not tree.exists() and "debug/case-a" in run_git(main, "branch").stdout
    assert "removed idle debug work copies debug-case-a" in str(line)


@pytest.mark.sr("SR-401")
def test_sr401_ex2_a_copy_for_an_open_problem_stays(main: Path) -> None:
    debug.open_case(main, id="case-a", kind="hook-error", target="stop", detail="boom")
    tree = copy(main, "case-a")
    assert landing.remove_idle(main) == ([], []) and tree.exists()


@pytest.mark.sr("SR-401")
def test_sr401_ex3_a_copy_with_uncommitted_changes_stays_and_is_named(main: Path) -> None:
    tree = copy(main, "case-a")
    (tree / "README.md").write_text("edited\n", encoding="utf-8")
    removed, kept = landing.remove_idle(main)
    assert removed == [] and tree.exists()
    assert kept == ["debug work copy debug-case-a is idle but kept: uncommitted changes"]


@pytest.mark.sr("SR-401")
def test_sr401_ex4_a_copy_with_an_unmerged_fix_is_untouched(main: Path) -> None:
    tree = copy(main, "case-a")
    docs(tree, "fix.md")
    commit_all(tree, "fix")
    assert landing.remove_idle(main) == ([], []) and tree.exists()
    assert cli.main(["debug", "prune", "--root", str(main)]) == 0 and tree.exists()


@pytest.mark.sr("SR-401")
def test_sr401_ex5_prune_removes_every_idle_copy_and_says_how_many(
        main: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trees = [copy(main, c) for c in ("case-a", "case-b", "case-c")]
    assert cli.main(["debug", "prune", "--root", str(main)]) == 0
    assert not any(t.exists() for t in trees)
    assert "removed 3 idle work copies" in capsys.readouterr().out


@pytest.mark.sr("SR-401")
def test_sr401_ex6_a_worktree_outside_the_debug_folder_is_untouched(main: Path,
                                                                     tmp_path: Path) -> None:
    other = tmp_path / "wt-feat"
    run_git(main, "worktree", "add", "-q", "-b", "feat", str(other))
    odd = main / ".plumb" / "wt" / "notes"
    run_git(main, "worktree", "add", "-q", "-b", "notes", str(odd))
    assert landing.remove_idle(main) == ([], []) and other.exists() and odd.exists()


@pytest.mark.sr("SR-402")
def test_sr402_ex1_below_the_floor_no_copy_is_made_and_the_idle_ones_are_named(
        main: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    idle = copy(main, "case-a")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: LOW)
    with pytest.raises(selfdebug.DiskShort) as why:
        copy(main, "case-b")
    text = str(why.value)
    assert "2.0 GB free" in text and "debug-case-a" in text and "plumb debug prune" in text
    assert not (main / ".plumb" / "wt" / "debug-case-b").exists() and idle.exists()


@pytest.mark.sr("SR-402")
def test_sr402_ex2_with_room_the_copy_is_made(main: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda p: HIGH)
    assert copy(main, "case-b").exists()


@pytest.mark.sr("SR-402")
def test_sr402_ex3_below_the_floor_with_nothing_idle_says_so(
        main: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda p: LOW)
    with pytest.raises(selfdebug.DiskShort, match="no idle copy could be removed"):
        copy(main, "case-b")


@pytest.mark.sr("SR-402")
def test_sr402_ex4_an_existing_copy_is_reused_below_the_floor(
        main: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = copy(main, "case-a")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: LOW)
    assert copy(main, "case-a") == tree


@pytest.mark.sr("SR-402")
def test_sr402_a_refused_fix_leaves_the_case_open(main: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.api import open_core

    (main / "pyproject.toml").write_text('[project]\nname = "plumb"\n', "utf-8")
    (main / "src" / "plumb").mkdir(parents=True)
    (main / "src" / "plumb" / "__init__.py").write_text("", "utf-8")
    commit_all(main, "plumb-shaped")
    debug.open_case(main, id="case-a", kind="hook-error", target="stop", detail="boom")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: LOW)
    out = selfdebug.fix(open_core(main), {"id": "case-a", "kind": "hook-error",
                                          "target": "stop", "detail": "boom"})
    assert out.state == "refused" and "floor is 5 GB" in out.detail
    assert [c["id"] for c in debug.open_cases(main)] == ["case-a"]
