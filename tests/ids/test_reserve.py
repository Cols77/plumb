"""IDS I1, I2: reservation through refs/plumb/ids with compare-and-swap (sp6 4.1, 4.2, 4.4).

SR-070 EX-1 (two worktrees), EX-3 (a moved ref retries), EX-5 (outside git)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ids.gitrepo import add_worktree, make_repo, run_git, write
from plumb import ids
from plumb.cli import main
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-257")


def ref_data(root: Path) -> dict:
    oid = run_git(root, "rev-parse", "-q", "--verify", ids.REF).strip()
    return json.loads(run_git(root, "cat-file", "blob", oid))


def ref_oid(root: Path) -> str:
    return run_git(root, "rev-parse", "-q", "--verify", ids.REF, check=False).strip()


def test_first_reserve_creates_ref_and_returns_next(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    write(root, "SR-004", "four")
    assert ref_oid(root) == ""
    assert ids.reserve(PlumbPaths(root), "requirement") == ["SR-005"]
    data = ref_data(root)
    assert data["v"] == 1 and data["high"]["SR"] == 5
    assert data["recent"][-1]["id"] == "SR-005"
    assert data["recent"][-1]["branch"] == "main"
    assert ids.reserve(PlumbPaths(root), "requirement") == ["SR-006"]


def test_two_worktrees_never_get_the_same_id(tmp_path: Path) -> None:
    main_root = make_repo(tmp_path / "main")
    write(main_root, "SR-069", "sixty-nine")
    run_git(main_root, "add", "-A")
    run_git(main_root, "commit", "-q", "-m", "sr 69")
    other = add_worktree(main_root, tmp_path / "feat", "feat-x")
    got: list[str] = []
    for _ in range(3):  # interleaved: neither worktree sees the other's files
        got += ids.reserve(PlumbPaths(main_root), "requirement")
        got += ids.reserve(PlumbPaths(other), "requirement")
    assert got[:2] == ["SR-070", "SR-071"]
    assert len(set(got)) == len(got) == 6
    assert ref_data(other)["high"]["SR"] == 75 == ref_data(main_root)["high"]["SR"]


_WORKER = """
import sys
from pathlib import Path
from plumb import ids
from plumb.ids import reservation
from plumb.paths import PlumbPaths
reservation.RETRIES, reservation.RETRY_S = 1000, 100.0  # a loaded machine must not exhaust the default budget
out = []
for _ in range(10):
    out += ids.reserve(PlumbPaths(Path(sys.argv[1])), "requirement")
print(" ".join(out))
"""


def test_concurrent_processes_get_distinct_ids(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    procs = [subprocess.Popen([sys.executable, "-c", _WORKER, str(root)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(2)]
    outs = [p.communicate(timeout=120) for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    got = [i for out, _ in outs for i in out.split()]
    assert len(got) == 20 and len(set(got)) == 20
    assert ref_data(root)["high"]["SR"] == max(int(i.split("-")[1]) for i in got) == 20


def test_moved_ref_retries_and_never_reuses(tmp_path: Path, monkeypatch) -> None:
    from plumb.ids import ref as ref_mod

    root = make_repo(tmp_path / "r")
    real_read = ref_mod.read
    calls = {"n": 0}

    def racing_read(r: Path):
        stale = real_read(r)
        calls["n"] += 1
        if calls["n"] == 1:  # another session reserves between our read and our update
            monkeypatch.setattr(ref_mod, "read", real_read)
            assert ids.reserve(PlumbPaths(root), "requirement") == ["SR-001"]
            monkeypatch.setattr(ref_mod, "read", racing_read)
        return stale

    monkeypatch.setattr(ref_mod, "read", racing_read)
    assert ids.reserve(PlumbPaths(root), "requirement") == ["SR-002"]
    assert calls["n"] >= 2
    assert ref_data(root)["high"]["SR"] == 2


def test_busy_ref_gives_up_with_exit_2(tmp_path: Path, monkeypatch, capsys) -> None:
    from plumb.ids import ref as ref_mod
    from plumb.ids import reservation as reserve_mod

    root = make_repo(tmp_path / "r")
    monkeypatch.setattr(reserve_mod, "RETRY_S", 0.2)

    def always_moved(*args, **kwargs):
        raise ref_mod.Moved("the ref moved")

    monkeypatch.setattr(ref_mod, "update", always_moved)
    code = main(["new", "requirement", "--title", "t", "--root", str(root)])
    err = capsys.readouterr().err
    assert code == 2
    assert "could not reserve an ID" in err and "Traceback" not in err
    assert not (root / ".plumb" / "requirements" / "SR-001.md").exists()


def test_batch_reserves_once_per_prefix(tmp_path: Path, monkeypatch) -> None:
    from plumb.ids import ref as ref_mod

    root = make_repo(tmp_path / "r")
    updates: list[str] = []
    real_update = ref_mod.update

    def counting(r, data, old, message):
        updates.append(message)
        return real_update(r, data, old, message)

    monkeypatch.setattr(ref_mod, "update", counting)
    assert ids.reserve(PlumbPaths(root), "requirement", 3) == ["SR-001", "SR-002", "SR-003"]
    assert len(updates) == 1
    assert ref_data(root)["high"]["SR"] == 3


def test_peek_does_not_move_the_ref(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    assert ids.peek(PlumbPaths(root), "requirement") == "SR-001"
    assert ref_oid(root) == ""
    ids.reserve(PlumbPaths(root), "requirement")
    before = ref_oid(root)
    assert ids.peek(PlumbPaths(root), "requirement") == "SR-002"
    assert ref_oid(root) == before


def test_no_git_falls_back_and_says_not_reserved(tmp_path: Path, capsys) -> None:
    from plumb.commands import init_repo

    root = tmp_path / "plain"
    root.mkdir()
    init_repo(root)
    write(root, "SR-079", "seventy-nine")
    assert main(["new", "requirement", "--title", "t", "--root", str(root)]) == 0
    captured = capsys.readouterr()
    assert (root / ".plumb" / "requirements" / "SR-080.md").exists()
    assert "SR-080 is not reserved (no git repository)" in captured.err
    assert ids.state(PlumbPaths(root)).reserved is False


def test_ic_prefix_three_digits(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    assert ids.reserve(PlumbPaths(root), "conflict") == ["IC-001"]
    assert ids.reserve(PlumbPaths(root), "conflict", 2) == ["IC-002", "IC-003"]
    assert ref_data(root)["high"]["IC"] == 3


def test_nc_four_digits(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    write(root, "NC-0041", "forty-one")
    assert ids.reserve(PlumbPaths(root), "nc") == ["NC-0042"]
