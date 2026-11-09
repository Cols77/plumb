"""IDS I3: seeding refs/iaso/ids from every local branch, observing, ``iaso ids sync``
(sp6 4.3). SR-070 EX-2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ids.gitrepo import commit_all, make_repo, iaso, run_git, write
from iaso import ids
from iaso.ids import ref as ref_mod
from iaso.paths import IasoPaths

pytestmark = pytest.mark.sr("SR-257")


def high(root: Path) -> dict:
    oid = run_git(root, "rev-parse", "-q", "--verify", ids.REF).strip()
    return json.loads(run_git(root, "cat-file", "blob", oid))["high"]


def test_seed_from_an_unchecked_out_branch(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    run_git(root, "checkout", "-q", "-b", "other")
    write(root, "SR-075", "on another branch")
    commit_all(root, "sr 75")
    run_git(root, "checkout", "-q", "main")
    assert not (root / ".iaso" / "requirements" / "SR-075.md").exists()
    assert ids.reserve(IasoPaths(root), "requirement") == ["SR-076"]
    assert high(root)["SR"] == 76


def test_seed_runs_once_per_clone(tmp_path: Path, monkeypatch) -> None:
    from iaso.ids import reservation

    root = make_repo(tmp_path / "r")
    calls = {"n": 0}
    real = reservation.branch_tips_high

    def counting(r: Path) -> dict:
        calls["n"] += 1
        return real(r)

    monkeypatch.setattr(reservation, "branch_tips_high", counting)
    ids.reserve(IasoPaths(root), "requirement")
    ids.reserve(IasoPaths(root), "decision")
    ids.reserve(IasoPaths(root), "requirement")
    assert calls["n"] == 1


def test_observe_raises_high_for_imported_ids(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path / "r")
    ids.reserve(IasoPaths(root), "requirement")
    ids.observe(IasoPaths(root), ["SR-040", "NC-0007", "DEC-002"])
    assert high(root) == {"SR": 40, "NC": 7, "DEC": 2}
    updates: list[str] = []
    real = ref_mod.update
    monkeypatch.setattr(ref_mod, "update",
                        lambda *a, **k: updates.append("x") or real(*a, **k))
    ids.observe(IasoPaths(root), ["SR-010"])  # already covered: nothing written
    assert updates == []
    assert ids.reserve(IasoPaths(root), "requirement") == ["SR-041"]


def test_ids_sync_rescans(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "r")
    ids.reserve(IasoPaths(root), "requirement")  # the ref exists: no seed scan again
    run_git(root, "checkout", "-q", "-b", "late")
    write(root, "SR-030", "made on a branch the seed never saw")
    commit_all(root, "sr 30")
    run_git(root, "checkout", "-q", "main")
    assert high(root)["SR"] == 1
    result = iaso(root, "ids", "sync", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["high"]["SR"] == 30
    status = iaso(root, "ids")
    assert status.returncode == 0 and "SR 30" in status.stdout
