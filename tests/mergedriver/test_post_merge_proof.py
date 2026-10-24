"""SR-341: a proof agreed as post-merge when it is chosen does not hold the merge into main
(EX-1); right after the landing the next turn tells the agent to show it and ask the owner
(EX-2); a proof not agreed as post-merge and not shown still holds (EX-3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import commit_all, make_repo, run_git
from mergedriver.test_merge_holds import _answer, _branch, _change, _sr001
from plumb.api import open_core
from plumb.boundary import landing
from plumb.boundary.premerge import check
from plumb.capture import proof

pytestmark = pytest.mark.sr("SR-341")

PLAN = "reload the plugin from main and see the panel"


def _delivering(tmp_path: Path, post_merge: bool) -> Path:
    """main holds SR-001; feat-x delivers it with a live-session proof planned, not shown."""
    root = make_repo(tmp_path / "main")
    _sr001(root)
    commit_all(root, "SR-001")
    feat = _branch(root, "feat-x", tmp_path / "feat")
    proof.set_plan(open_core(feat), "SR-001", PLAN, "live-session", post_merge or None)
    _change(feat, "src/x.py", "deliver\n\nSR: SR-001")
    _change(root, "notes.txt", "main side")
    return root


def test_ex1_a_post_merge_proof_does_not_hold_the_merge(tmp_path: Path) -> None:
    root = _delivering(tmp_path, post_merge=True)
    run_git(root, "merge", "--no-commit", "--no-ff", "--no-verify", "feat-x")
    report = check(open_core(root))
    assert report.proofs == () and report.exit == 0, report.lines
    assert proof.proof_lines(open_core(root).index()["SR-001"])[0].startswith(
        "SR-001 proof (live-session, post-merge)")


def test_ex3_a_proof_not_agreed_as_post_merge_still_holds(tmp_path: Path) -> None:
    root = _delivering(tmp_path, post_merge=False)
    run_git(root, "merge", "--no-commit", "--no-ff", "--no-verify", "feat-x")
    report = check(open_core(root))
    assert [(r["id"], r["why"]) for r in report.proofs] == [("SR-001", "not shown working")]
    assert report.exit == 5


def test_ex2_the_turn_after_the_landing_asks_for_the_post_merge_proof(
        tmp_path: Path, hook_input) -> None:
    root = _delivering(tmp_path, post_merge=True)
    before = run_git(root, "rev-parse", "HEAD").stdout.strip()
    run_git(root, "merge", "-q", "--no-ff", "--no-verify", "-m", "m", "feat-x")
    head = run_git(root, "rev-parse", "HEAD").stdout.strip()
    result = landing.land(root, head, before)
    assert result["post_merge"] == ["SR-001"]
    asks = [text for key, text in landing.lines(root) if key == "post-merge-proof:SR-001"]
    assert len(asks) == 1 and PLAN in asks[0] and "plumb proof SR-001 --ask" in asks[0]
    # shown and confirmed by the owner: the next turn no longer asks
    proof.set_evidence(open_core(root), "SR-001", "https://x.test/run", "the panel drew",
                       passed=True)
    _answer(root, hook_input, proof.ask(open_core(root), "SR-001", "test-session"), proof.YES)
    assert not [k for k, _ in landing.lines(root) if k.startswith("post-merge-proof:")]
