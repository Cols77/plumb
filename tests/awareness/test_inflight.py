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

pytestmark = pytest.mark.sr("SR-258")


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



def test_slow_git_under_load_still_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                                           ) -> None:
    """SR-258 EX-11 under load: git calls slower than the retry budget and a racing
    writer; the loser of the race still retries and both claims are kept."""
    main, other = setup(tmp_path)
    real = inflight._git
    moved = {"done": False}

    def slow_racing(root, *args, stdin=None):  # noqa: ANN001, ANN202
        if args[0] == "update-ref" and not moved["done"]:
            moved["done"] = True
            inflight.record_claim(open_core(other), records={"SR-006": {"title": "card"}},
                                  summary="other work", intent="INT-009")
        inflight.time.sleep(0.03)                 # each git call outlasts retry_s
        return real(root, *args, stdin=stdin)

    monkeypatch.setattr(inflight, "_git", slow_racing)
    inflight.update(main, lambda d: {**d, "claims": [*d["claims"], {"id": "main:INT-001"}]},
                    retry_s=0.02)
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


# -- a claim clears exactly when its branch merges (R17): one test per way a claim is read
#    or pruned (the hook-free read, the git read, a writer's pruning, the session start)


def _branches(root: Path, *, allow_git: bool = True) -> list[str]:
    return [c["branch"] for c in inflight.others(open_core(root), allow_git=allow_git)[1]]


def _refreshed_at_tip(tmp_path: Path) -> tuple[Path, Path]:
    """feat-x claims SR-005, commits, then refreshes its claim at the commit (as a capture
    or the stop hook does after a commit in the same turn)."""
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    head = commit_all(other, "feat-x work")
    inflight.record_claim(open_core(other), records={}, summary="", intent="INT-001")
    [claim] = _claims(main)
    assert claim["head"] == head and claim["own"] == head
    return main, other


def test_claim_refreshed_at_the_tip_clears_on_merge(tmp_path: Path) -> None:
    """The git read: a claim written at the branch tip clears once that tip merges."""
    main, _other = _refreshed_at_tip(tmp_path)
    assert _branches(main) == ["feat-x"]
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    assert _branches(main) == []


def test_claim_refreshed_at_the_tip_clears_on_fast_forward_merge(tmp_path: Path) -> None:
    main, _other = _refreshed_at_tip(tmp_path)
    run_git(main, "merge", "-q", "--ff-only", "feat-x")
    assert _branches(main) == []


def test_merged_claim_is_pruned_by_the_next_writer(tmp_path: Path) -> None:
    """A writer's pruning: the next claim from any branch drops the merged one."""
    main, _other = _refreshed_at_tip(tmp_path)
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    inflight.record_claim(open_core(main), records={"SR-006": {"title": "status card"}},
                          summary="main work", intent="INT-009")
    assert [c["branch"] for c in _claims(main)] == ["main"]


def test_session_start_drops_a_claim_refreshed_at_the_tip(tmp_path: Path) -> None:
    """The hook-free read keeps what it cannot know; the session start learns it."""
    from plumb.awareness.turn import at_session_start

    main, _other = _refreshed_at_tip(tmp_path)
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    assert _branches(main, allow_git=False) == ["feat-x"]
    at_session_start(open_core(main))
    assert _branches(main, allow_git=False) == []


def test_stop_hook_moves_the_claim_to_a_new_commit(tmp_path: Path) -> None:
    """The stop hook after a commit with no record change moves the branch's claims to its
    tip, so a fast-forward merge of that commit clears them."""
    from plumb.awareness import publish as pub
    from plumb.awareness.turn import claim_changes

    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    head = commit_all(other, "feat-x work")
    data = pub.publish(open_core(other), [])
    assert claim_changes(open_core(other), data) is True
    assert _claims(main)[0]["own"] == head
    assert claim_changes(open_core(other), data) is False        # nothing moved since
    run_git(main, "merge", "-q", "--ff-only", "feat-x")
    assert _branches(main) == []


def _fast_forwarded_to_main(tmp_path: Path) -> tuple[Path, Path]:
    """feat-x captured intent (uncommitted); main moved on; feat-x fast-forwards to main."""
    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    (main / "README.md").write_text("main moved on\n", encoding="utf-8")
    commit_all(main, "main work")
    run_git(other, "merge", "-q", "--ff-only", "main")
    return main, other


def test_fast_forward_to_main_keeps_the_claim(tmp_path: Path) -> None:
    """The git read: a branch that only took main's commits has merged nothing."""
    main, _other = _fast_forwarded_to_main(tmp_path)
    assert _branches(main) == ["feat-x"]


def test_fast_forward_to_main_survives_another_writer(tmp_path: Path) -> None:
    """A writer's pruning keeps it too, with its raised conflicts."""
    main, _other = _fast_forwarded_to_main(tmp_path)

    def note(data: dict) -> dict:
        data["claims"][0]["conflicts"] = [{"record": "SR-005", "branch": "main",
                                           "dec": "DEC-001", "state": "confirmed",
                                           "chosen": "feat-x's version"}]
        return data

    inflight.update(main, note)
    inflight.record_claim(open_core(main), records={"SR-006": {"title": "status card"}},
                          summary="main work", intent="INT-009")
    [kept] = [c for c in _claims(main) if c["branch"] == "feat-x"]
    assert kept["conflicts"][0]["dec"] == "DEC-001"


def test_fast_forward_to_main_survives_the_stop_hook_and_session_start(tmp_path: Path
                                                                       ) -> None:
    from plumb.awareness import publish as pub
    from plumb.awareness.turn import at_session_start, claim_changes

    main, other = _fast_forwarded_to_main(tmp_path)
    claim_changes(open_core(other), pub.publish(open_core(other), []))
    at_session_start(open_core(main))
    assert _branches(main, allow_git=False) == ["feat-x"]
    assert _branches(main) == ["feat-x"]


# -- a merged branch has nothing committed in flight (R17: a claim clears when its branch
#    merges, and stays cleared): one test per entry point that writes a claim or reads what a
#    worktree is changing


def _merged_and_pruned(tmp_path: Path) -> tuple[Path, Path]:
    """feat-x claims SR-005, commits, its stop hook runs; main merges feat-x; the next
    writer prunes the merged claim. feat-x's worktree stays open."""
    from plumb.awareness import publish as pub
    from plumb.awareness.turn import claim_changes

    main, other = setup(tmp_path)
    change(other, "feat-x's version")
    commit_all(other, "feat-x work")
    claim_changes(open_core(other), pub.publish(open_core(other), []))
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    inflight.record_claim(open_core(main), records={"SR-006": {"title": "status card"}},
                          summary="main work", intent="INT-009")
    assert [c["branch"] for c in _claims(main)] == ["main"]
    return main, other


def test_stop_hook_after_the_merge_claims_nothing(tmp_path: Path) -> None:
    """The stop hook (claim_changes): the merged records are not claimed again, so a later
    change on main asks nothing."""
    from plumb.awareness import publish as pub
    from plumb.awareness.turn import claim_changes

    main, other = _merged_and_pruned(tmp_path)
    data = pub.publish(open_core(other), [])
    assert data is not None and data["committed"] == [] and data["records"] == {}
    assert claim_changes(open_core(other), data) is False
    assert _branches(main) == []
    result = change(main, "main's later version")
    assert not any("Conflict" in line for line in result.lines)


def test_inflight_sync_after_the_merge_claims_nothing(tmp_path: Path) -> None:
    """``plumb inflight sync``."""
    import contextlib
    import io

    from plumb.cli import main as cli_main

    main, other = _merged_and_pruned(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        assert cli_main(["inflight", "sync", "--root", str(other)]) == 0
    assert _branches(main) == []


def test_capture_after_the_merge_claims_only_what_it_changed(tmp_path: Path) -> None:
    """Capture (after_capture): new intent on feat-x is claimed; the merged record is not."""
    main, other = _merged_and_pruned(tmp_path)
    change(other, "feat-x's next status card", record="SR-006")
    [claim] = [c for c in _claims(main) if c["branch"] == "feat-x"]
    assert set(claim["records"]) == {"SR-006"}


def test_publish_keeps_pending_edits_when_only_main_moved(tmp_path: Path) -> None:
    """``changing.json``: main moving (here: merging feat-x) empties the committed part and
    keeps the edits since the last commit."""
    from plumb.awareness import publish as pub

    main, other = _merged_and_pruned(tmp_path)
    (other / "notes.txt").write_text("after the merge\n", encoding="utf-8")
    pub.note_edit(other, "notes.txt")
    data = pub.publish(open_core(other), [])
    assert data is not None and data["committed"] == [] and data["pending"] == ["notes.txt"]


def test_other_worktrees_stop_naming_a_merged_branch(tmp_path: Path) -> None:
    """The overlap read of another worktree's ``changing.json``: feat-x's file still lists
    SR-005 as committed (feat-x ran no hook since the merge); main's session start learns
    the merge (one git call, cached) and every later hook read ignores it."""
    from plumb.awareness import scan
    from plumb.awareness.turn import at_session_start

    main, _other = _merged_and_pruned(tmp_path)
    assert {o.branch for o in scan.overlaps(open_core(main), ["SR-005"])} == {"feat-x"}
    at_session_start(open_core(main))
    assert [o for o in scan.overlaps(open_core(main), ["SR-005"])
            if o.branch == "feat-x"] == []
