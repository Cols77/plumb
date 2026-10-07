"""R17: the refs/plumb/claims register of intent in flight (SR-080)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from awareness.gitrepo import commit_all, run_git
from awareness.scenario import change, setup
from plumb.api import open_core
from plumb.awareness import inflight

pytestmark = pytest.mark.sr("SR-080")


def _claims(root: Path) -> list[dict]:
    _oid, data = inflight.read(root, allow_git=True)
    return data["claims"]


def test_capture_records_a_claim(tmp_path: Path) -> None:
    """SR-080 EX-1: a capture on feat-x claims SR-005 with the branch and a summary."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    claims = _claims(main)                        # every worktree sees one register
    assert len(claims) == 1
    claim = claims[0]
    assert claim["branch"] == "feat-x"
    assert claim["summary"] == "relay intent"
    assert set(claim["records"]) == {"SR-005"}
    assert claim["records"]["SR-005"]["text"] == ("A relay pins the stated group, named by its "
                                                  "title.")
    assert claim["features"] == ["FEAT-002"]
    assert run_git(main, "cat-file", "-t", inflight.REF).strip() == "blob"


def test_concurrent_claims_are_both_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                                         ) -> None:
    """SR-080 EX-2: the ref moved between this writer's read and its update: it retries,
    and no claim is lost."""
    main, other = setup(tmp_path)
    real = inflight._git
    moved = {"done": False}

    def racing(root, *args, stdin=None):  # noqa: ANN001, ANN202
        if args[:1] == ("update-ref",) and not moved["done"]:
            moved["done"] = True
            inflight.record_claim(open_core(other), records={"SR-006": {"title": "status card"}},
                                  summary="other work", intent="INT-009")
        return real(root, *args, stdin=stdin)

    monkeypatch.setattr(inflight, "_git", racing)
    inflight.record_claim(open_core(main), records={"SR-005": {"title": "relay checks"}},
                          summary="main work", intent="INT-001")
    assert sorted(c["id"] for c in _claims(main)) == ["feat-x:INT-009", "main:INT-001"]


_WORKER = """
import sys
from pathlib import Path
from plumb.api import open_core
from plumb.awareness import inflight
root, tag = Path(sys.argv[1]), sys.argv[2]
for n in range(5):
    inflight.record_claim(open_core(root), records={f"SR-00{n}": {"title": tag}},
                          summary=tag, intent=f"INT-{tag}{n}")
"""


def test_two_processes_lose_nothing(tmp_path: Path) -> None:
    """SR-080 EX-2 with two real processes writing at once."""
    main, other = setup(tmp_path)
    procs = [subprocess.Popen([sys.executable, "-c", _WORKER, str(root), tag])
             for root, tag in ((main, "a"), (other, "b"))]
    assert [p.wait(timeout=120) for p in procs] == [0, 0]
    ids = sorted(c["id"] for c in _claims(main))
    assert ids == sorted([f"main:INT-a{n}" for n in range(5)]
                         + [f"feat-x:INT-b{n}" for n in range(5)])


def test_claim_clears_when_branch_merged_or_deleted(tmp_path: Path) -> None:
    """SR-080 EX-3: merged into main (or deleted), the claim is gone."""
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    assert [c["branch"] for c in inflight.others(open_core(main), allow_git=True)[1]] == [
        "feat-x"]
    commit_all(other, "feat-x work")
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    assert inflight.others(open_core(main), allow_git=True)[1] == []
    # deleted: a claim on a branch that no longer exists
    run_git(main, "branch", "-q", "feat-y")
    run_git(main, "worktree", "add", "-q", str(tmp_path / "wt-y"), "feat-y")
    change(tmp_path / "wt-y", "feat-y's version", record="SR-006")
    assert [c["branch"] for c in inflight.others(open_core(main), allow_git=True)[1]] == [
        "feat-y"]
    run_git(main, "worktree", "remove", "--force", str(tmp_path / "wt-y"))
    run_git(main, "branch", "-q", "-D", "feat-y")
    assert inflight.others(open_core(main), allow_git=True)[1] == []


def test_unmerged_branch_keeps_its_claim_after_commits(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    commit_all(other, "feat-x work")
    assert [c["branch"] for c in inflight.others(open_core(main), allow_git=True)[1]] == [
        "feat-x"]


def test_claim_never_refuses_anything(tmp_path: Path) -> None:
    """SR-080 EX-4: another branch claims SR-005; this worktree's capture and edits of
    SR-005 go through."""
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    result = change(main, "main's version")
    assert "SR-005" in result.updated
    record = (main / ".plumb" / "requirements" / "SR-005.md").read_text(encoding="utf-8")
    assert "main's version" in record
    (main / ".plumb" / "requirements" / "SR-005.md").write_text(record + "\n",
                                                                encoding="utf-8")


def test_drop_removes_the_branch_claims(tmp_path: Path) -> None:
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    assert inflight.drop(open_core(main), "feat-x") == ["feat-x:INT-001"]
    assert _claims(main) == []


def test_hook_read_needs_no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The register is read from git's files (a loose blob) on a hook path."""
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    (main / ".plumb" / "cache" / inflight.CACHE).unlink(missing_ok=True)

    def refuse(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("git process")

    monkeypatch.setattr(subprocess, "run", refuse)
    _oid, data = inflight.read(main)
    assert [c["branch"] for c in data["claims"]] == ["feat-x"]


def test_session_start_drops_a_merged_branch_claim(tmp_path: Path) -> None:
    """The hook path keeps a claim whose reachability it cannot know without git; the
    session start learns (with git, cached) that its branch merged, and every later hook
    read drops it."""
    from plumb.awareness.turn import at_session_start

    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    commit_all(other, "feat-x work")
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    assert [c["branch"] for c in inflight.others(open_core(main))[1]] == ["feat-x"]
    at_session_start(open_core(main))
    assert inflight.others(open_core(main))[1] == []
