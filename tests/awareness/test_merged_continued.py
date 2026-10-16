"""R17: a claim clears when its branch merges, record by record, even when the branch goes
on after the merge (SR-080). One test per entry point that reads the register: capture, the
clarify read-back, the stop hook's claim, the brief and the status section; plus one per way
a merged record is recognised (the default branch holds its version; the commit that wrote
it merged; the branch no longer changes it).

Scenario: feat-x changes SR-005 and commits; main merges feat-x with --no-ff; feat-x gets
one more (unrelated) commit; main then changes SR-005. Nothing is in conflict: main already
holds feat-x's version, so no card, no question and no decision."""

from __future__ import annotations

from pathlib import Path

import pytest

from awareness.gitrepo import commit_all, run_git, write_record
from awareness.scenario import change, setup
from plumb.api import open_core
from plumb.awareness import inflight
from plumb.awareness import publish as pub

pytestmark = pytest.mark.sr("SR-258")


def _stop_hook(root: Path, changed: list[str] | None = None) -> list[str]:
    """The stop hook's awareness step (publish, then the claim kept in step)."""
    from plumb.awareness.early import turn_cards
    from plumb.awareness.turn import claim_changes

    claim_changes(open_core(root), pub.publish(open_core(root), changed or []))
    return turn_cards(open_core(root).paths.session)[0]


def _merged_then_continued(tmp_path: Path, *, hooks: bool = True,
                           main_moves: bool = False) -> tuple[Path, Path]:
    """feat-x claims SR-005 and commits (its stop hook runs when ``hooks``); main merges
    feat-x (--no-ff), then, with ``main_moves``, commits a later SR-005 of its own; feat-x
    commits one more unrelated change and (with ``hooks``) runs its session start and stop
    hook."""
    from plumb.awareness.turn import at_session_start

    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    commit_all(other, "feat-x work")
    if hooks:
        _stop_hook(other)
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    if main_moves:
        write_record(main, "SR-005", "relay checks", feature="FEAT-002",
                     statement="A relay pins the stated group and says so.")
        commit_all(main, "main's later relay checks")
    (other / "notes.txt").write_text("after the merge\n", encoding="utf-8")
    commit_all(other, "feat-x goes on")
    if hooks:
        at_session_start(open_core(other))
        _stop_hook(other)
    return main, other


def _decisions(root: Path) -> list[str]:
    return [r.id for r in open_core(root).index().values() if r.kind == "decision"]


def _feat_x(root: Path, *, allow_git: bool = True) -> list[dict]:
    return [c for c in inflight.others(open_core(root), allow_git=allow_git)[1]
            if c["branch"] == "feat-x"]


# -- one test per entry point


def test_capture_on_main_asks_nothing(tmp_path: Path) -> None:
    main, _other = _merged_then_continued(tmp_path)
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert not any("waits as a card" in line for line in result.lines), result.lines
    assert _decisions(main) == []


def test_clarify_read_back_on_main_asks_nothing(tmp_path: Path) -> None:
    from plumb.capture.clarify import clarify

    main, _other = _merged_then_continued(tmp_path)
    view = clarify(open_core(main), "make SR-005 relay checks pin only the affirmed records")
    assert not any("Conflict" in line for line in view.inflight), view.inflight


def test_stop_hook_claim_on_main_asks_nothing(tmp_path: Path) -> None:
    main, _other = _merged_then_continued(tmp_path)
    write_record(main, "SR-005", "relay checks", feature="FEAT-002",
                 statement="A relay pins only the records the owner's words affirm.")
    asked = _stop_hook(main, [".plumb/requirements/SR-005.md"])
    assert asked == []
    assert _decisions(main) == []


def test_brief_and_status_on_main_name_nothing_of_feat_x(tmp_path: Path) -> None:
    from plumb.awareness.lines import brief_lines, status_section
    from plumb.awareness.turn import at_session_start

    main, _other = _merged_then_continued(tmp_path)
    at_session_start(open_core(main))
    assert _feat_x(main, allow_git=False) == []          # the hook-free read
    assert not any("feat-x" in line for line in brief_lines(open_core(main)))
    assert not any("feat-x" in line for line in status_section(open_core(main)))


# -- one test per way a merged record is recognised


def test_default_branch_holding_the_version_clears_it_without_any_hook(tmp_path: Path
                                                                       ) -> None:
    """No hook ran on feat-x since its capture: the default branch holds the claimed
    version (same hash), so the record is not in flight."""
    main, _other = _merged_then_continued(tmp_path, hooks=False)
    assert _feat_x(main) == []
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert not any("Conflict" in line for line in result.lines)


def test_merged_commit_clears_it_after_main_moved_on(tmp_path: Path) -> None:
    """The stop hook stamped the commit that wrote feat-x's version; main merged it, then
    changed SR-005 again: the stamped commit is reachable from main, so it is gone even
    before feat-x runs another hook."""
    from plumb.awareness.turn import claim_changes

    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    head = commit_all(other, "feat-x work")
    claim_changes(open_core(other), pub.publish(open_core(other), []))
    [claim] = _feat_x(main)
    assert claim["records"]["SR-005"]["commit"] == head
    run_git(main, "merge", "-q", "--no-ff", "-m", "merge feat-x", "feat-x")
    write_record(main, "SR-005", "relay checks", feature="FEAT-002",
                 statement="A relay pins the stated group and says so.")
    commit_all(main, "main's later relay checks")
    (other / "notes.txt").write_text("after the merge\n", encoding="utf-8")
    commit_all(other, "feat-x goes on")
    assert _feat_x(main) == []
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert not any("Conflict" in line for line in result.lines)


def test_refresh_rebuilds_the_records_from_what_the_branch_still_changes(tmp_path: Path
                                                                          ) -> None:
    """No hook stamped feat-x's commit before the merge, and main moved SR-005 on: when
    feat-x's stop hook moves its claim to the new tip, SR-005 (unchanged since the new merge
    base) is not carried forward."""
    main, other = _merged_then_continued(tmp_path, hooks=False, main_moves=True)
    _stop_hook(other)
    _oid, data = inflight.read(main, allow_git=True)
    assert not any("SR-005" in (c.get("records") or {}) for c in data["claims"]
                   if c["branch"] == "feat-x")
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert not any("Conflict" in line for line in result.lines)


def test_unmerged_change_still_conflicts(tmp_path: Path) -> None:
    """The guarantee's other side: a version feat-x has NOT merged is still in flight."""
    main, other = setup(tmp_path)
    change(other, "A relay pins the stated group, named by its title.")
    commit_all(other, "feat-x work")
    _stop_hook(other)
    (other / "notes.txt").write_text("more\n", encoding="utf-8")
    commit_all(other, "feat-x goes on")
    _stop_hook(other)
    result = change(main, "A relay pins only the records the owner's words affirm.")
    assert any("waits as a card" in line for line in result.lines)
