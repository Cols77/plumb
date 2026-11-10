"""R17, R2: an early intent-conflict card read on a branch that is neither side (the default
branch after one side merged) labels both versions by branch, never "this work";
the owner's choice there names a branch, and an open merge conflict on the same record is
the one card asked (SR-081 EX-10). One test per entry point: /iaso conflicts, the stop
hook's card and ``conflict choose``, each run from the default
branch."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import pytest
from mergedriver.mdhelpers import install_driver

from awareness.gitrepo import add_worktree, commit_all, make_repo, run_git, write_record
from awareness.scenario import capture
from iaso import cli
from iaso.api import open_core
from iaso.awareness import early

pytestmark = pytest.mark.sr("SR-259")
A = "A reminder is sent 48 hours before the deadline."
B = "A reminder is sent 2 hours before the deadline."


def _lanes(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """feat-a captures A for SR-005, feat-b captures B (the early decision is raised on
    feat-b, unanswered); both commit. Returns main, the two worktrees and the decision."""
    main = make_repo(tmp_path / "main")
    install_driver(main)
    write_record(main, "FEAT-002", "reminders", description="reminders")
    write_record(main, "INT-001", "reminder intent", quote="remind", readback="remind")
    write_record(main, "SR-005", "deadline reminder", feature="FEAT-002",
                 statement="A reminder is sent 24 hours before the deadline.")
    commit_all(main, "records")
    wta = add_worktree(main, tmp_path / "wt-a", "feat-a")
    wtb = add_worktree(main, tmp_path / "wt-b", "feat-b")
    capture(wta, {"intent": "INT-001", "updates": [{"id": "SR-005", "statement": A}]})
    capture(wtb, {"intent": "INT-001", "updates": [{"id": "SR-005", "statement": B}]})
    [dec] = [r.id for r in open_core(wtb).index().values() if r.kind == "decision"]
    commit_all(wta, "48 hours\n\nSR: SR-005")
    commit_all(wtb, "2 hours\n\nSR: SR-005")
    return main, wta, wtb, dec


def _on_main_after_b(tmp_path: Path) -> tuple[Path, str]:
    """main took feat-b (with its unanswered decision); feat-a is still in flight."""
    main, _wta, _wtb, dec = _lanes(tmp_path)
    run_git(main, "merge", "-q", "--no-edit", "feat-b")
    return main, dec


def _conflicts(root: Path, *words: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["conflicts", *words, "--root", str(root)]) == 0
    return out.getvalue()


def _state(root: Path, record_id: str) -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def test_conflicts_on_default_branch_labels_both_sides_by_branch(tmp_path: Path) -> None:
    main, _dec = _on_main_after_b(tmp_path)
    text = _conflicts(main)
    assert '▸ Conflict on "deadline reminder"' in text and "SR-005" not in text
    assert f"feat-b      {B}" in text and f"feat-a      {A}" in text
    assert "this work" not in text and "keep this one" not in text
    assert "Ask the owner with the question tool (feat-b's, feat-a's, or both)" in text


def test_stop_hook_conflict_on_default_branch_labels_both_sides(tmp_path: Path) -> None:
    """The conflict /iaso conflicts asks the stop hook to hand back is stated by branch."""
    main, _dec = _on_main_after_b(tmp_path)
    _conflicts(main)
    found = early.turn_conflicts(open_core(main).paths.session)
    assert [early.stated_entry(c) for c in found] == [
        {"record": "SR-005", "branch": "feat-b", "ours_label": "feat-a"}]


def test_choose_on_default_branch_takes_a_branch_name(tmp_path: Path) -> None:
    main, dec = _on_main_after_b(tmp_path)
    assert cli.main(["conflict", "choose", dec, "--take", "this one", "--root",
                     str(main)]) == 1
    assert _state(main, dec) == "proposed"
    assert cli.main(["conflict", "choose", dec, "--take", "feat-a", "--root", str(main)]) == 0
    assert open_core(main).index()[dec].fields["chosen"] == "feat-a's version"


def _held_merge_of_b(tmp_path: Path) -> tuple[Path, str]:
    """main took feat-a, then merges feat-b: the record merge leaves IC-001 on SR-005, and
    feat-b's unanswered decision on the same record comes in with it."""
    main, _wta, _wtb, dec = _lanes(tmp_path)
    run_git(main, "merge", "-q", "--no-edit", "feat-a")
    run_git(main, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-b", check=False)
    return main, dec


def test_conflicts_shows_one_card_per_record(tmp_path: Path) -> None:
    """/iaso conflicts and the stop hook's card: only the merge card asks."""
    main, _dec = _held_merge_of_b(tmp_path)
    text = _conflicts(main)
    assert text.count("▸ Conflict") == 1 and "Conflict IC-" in text
    assert early.turn_conflicts(open_core(main).paths.session) == []


def test_choose_of_the_decision_answers_through_the_merge_card(tmp_path: Path) -> None:
    """Choosing on the decision while the merge card asks the same question records the
    owner's choice on the merge card, which also answers the decision."""
    main, dec = _held_merge_of_b(tmp_path)
    assert cli.main(["conflict", "choose", dec, "--take", "feat-b", "--root", str(main)]) == 0
    core = open_core(main)
    record = core.index()["SR-005"]
    assert record.fields["statement"] == B and "conflict" not in record.fields
    assert core.index()[dec].fields["chosen"] == "feat-b's version"
    assert _state(main, dec) == "confirmed"
