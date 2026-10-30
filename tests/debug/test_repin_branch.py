"""SR-351: the repins of a debug pass in plumb's own main checkout land on a debug branch,
committed with the requirement trailer and announced as ready to land; the checkout stays
unchanged. The meaning cascade is stubbed to repin; git is real."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from plumb import debug, selfdebug
from plumb.api import open_core
from plumb.links import AfterTests, repin
from tests.debug.test_selffix import SR1, _git, plumb_repo  # noqa: F401 - fixture

pytestmark = pytest.mark.sr("SR-351")


def test_ex1_a_repin_is_a_commit_on_a_debug_branch_announced_and_main_is_unchanged(
        plumb_repo: Path, write_record, monkeypatch, capsys) -> None:  # noqa: F811
    write_record(plumb_repo, SR1.format(suffix=" of two numbers"))
    _git(plumb_repo, "commit", "-qam", "reword")   # DEC-001 is stale in main
    monkeypatch.setattr("plumb.links.repin_after_tests", lambda core, record, **kw: (
        AfterTests(changes=[{"link": c["link"], "tier": "tests pass"}
                            for c in repin(core, record, all_stale=True)])))
    head = _git(plumb_repo, "rev-parse", "HEAD")
    assert debug.run("debug", ["--root", str(plumb_repo)]) == 1   # the hook case stays open
    assert "DEC-001#0: resolved" in capsys.readouterr().out
    assert _git(plumb_repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert _git(plumb_repo, "rev-parse", "HEAD") == head
    assert _git(plumb_repo, "rev-list", "--count", "main..debug/repin").strip() == "1"
    assert "SR: SR-001" in _git(plumb_repo, "log", "-1", "--format=%B", "debug/repin")
    assert _git(plumb_repo, "status", "--porcelain", "--untracked-files=all",
                "--", ":!.plumb/wt") == ""
    assert all(s.state == "current" for s in open_core(
        plumb_repo / ".plumb" / "wt" / "debug-repin").link_states(["DEC-001"]))
    (key, text), = debug.lines(plumb_repo, "s1")
    assert key.startswith("ready:repin-") and "debug/repin" in text
    assert "reviewed" not in text


def test_the_trailer_names_only_requirements_still_in_the_tree(
        plumb_repo: Path, write_record, monkeypatch) -> None:  # noqa: F811
    """A link to a requirement that left the tree is not named: the commit check would refuse
    the whole repin."""
    from plumb.contracts import Target

    write_record(plumb_repo, SR1.replace("SR-001", "SR-002"))
    open_core(plumb_repo).add_link("DEC-001", "decides", Target(record="SR-002"))
    (plumb_repo / ".plumb" / "requirements" / "SR-002.md").unlink()
    write_record(plumb_repo, SR1.format(suffix=" of two numbers"))
    _git(plumb_repo, "add", "-A")
    _git(plumb_repo, "commit", "-qm", "reword; SR-002 leaves the tree")
    monkeypatch.setattr("plumb.links.repin_after_tests", lambda core, record, **kw: (
        AfterTests(changes=[{"link": c["link"], "tier": "tests pass"}
                            for c in repin(core, record, all_stale=True)])))
    debug.run("debug", ["--root", str(plumb_repo)])
    body = _git(plumb_repo, "log", "-1", "--format=%B", "debug/repin")
    assert "SR: SR-001\n" in body and "SR-002" not in body


@pytest.fixture
def stale_dec(plumb_repo: Path, write_record, monkeypatch) -> Path:
    write_record(plumb_repo, SR1.format(suffix=" of two numbers"))
    _git(plumb_repo, "commit", "-qam", "reword")
    monkeypatch.setattr("plumb.links.repin_after_tests", lambda core, record, **kw: (
        AfterTests(changes=[{"link": c["link"], "tier": "tests pass"}
                            for c in repin(core, record, all_stale=True)])))
    return plumb_repo


def test_a_second_pass_after_main_moved_replaces_the_first_announcement(stale_dec: Path) -> None:
    debug.run("debug", ["--root", str(stale_dec)])
    (stale_dec / "note.txt").write_text("x", "utf-8")
    _git(stale_dec, "add", "note.txt")
    _git(stale_dec, "commit", "-qm", "main moves")
    debug.run("debug", ["--root", str(stale_dec)])
    assert _git(stale_dec, "rev-list", "--count", "main..debug/repin").strip() == "1"
    assert _git(stale_dec, "merge-base", "main", "debug/repin").strip() == _git(
        stale_dec, "rev-parse", "main").strip()
    assert len(debug.lines(stale_dec, "s1")) == 1


def test_a_pass_that_changes_nothing_keeps_the_branch_and_its_announcement(
        stale_dec: Path) -> None:
    debug.run("debug", ["--root", str(stale_dec)])
    tip = _git(stale_dec, "rev-parse", "debug/repin")
    assert debug.on_branch(open_core(stale_dec), lambda c: None) == (None, "")
    assert len(debug.lines(stale_dec, "s1")) == 1
    assert _git(stale_dec, "rev-parse", "debug/repin") == tip


def test_dry_run_makes_no_branch(stale_dec: Path) -> None:
    debug.run("debug", ["--root", str(stale_dec), "--dry-run"])
    assert _git(stale_dec, "branch", "--list", "debug/repin") == ""


def test_a_failed_commit_reports_open_and_drops_the_edits(stale_dec: Path,
                                                          monkeypatch, capsys) -> None:
    real = selfdebug._git

    def boom(cwd, *args, **kw):
        if args[:1] == ("commit",):
            raise subprocess.CalledProcessError(1, "git commit", stderr="hook said no")
        return real(cwd, *args, **kw)

    monkeypatch.setattr(selfdebug, "_git", boom)
    debug.run("debug", ["--root", str(stale_dec)])
    assert "hook said no" in capsys.readouterr().out
    assert _git(stale_dec, "rev-list", "--count", "main..debug/repin").strip() == "0"
    assert debug.lines(stale_dec, "s1") == []


def test_main_uncommitted_work_is_not_touched(stale_dec: Path) -> None:
    (stale_dec / "src" / "plumb" / "calc.py").write_text("# edited", "utf-8")
    debug.run("debug", ["--root", str(stale_dec)])
    assert (stale_dec / "src" / "plumb" / "calc.py").read_text("utf-8") == "# edited"


def test_a_failure_in_the_work_reports_open_and_cleans_the_worktree(
        stale_dec: Path, capsys) -> None:
    def work(c):
        wt = stale_dec / ".plumb" / "wt" / "debug-repin"
        (wt / "junk.txt").write_text("x", "utf-8")
        raise RuntimeError("model fell over")

    found, error = debug.on_branch(open_core(stale_dec), work)
    assert "model fell over" in error
    wt = stale_dec / ".plumb" / "wt" / "debug-repin"
    assert not (wt / "junk.txt").exists()
    assert _git(wt, "status", "--porcelain") == ""
    assert debug._pass(open_core(stale_dec), [], False) is not None


def test_the_turn_end_settle_stays_in_place(stale_dec: Path) -> None:
    from plumb import stale

    stale.settle_drift(open_core(stale_dec), "s1", [SimpleNamespace(record="DEC-001")])
    assert _git(stale_dec, "branch", "--list", "debug/repin") == ""
