"""R17: a merge-time intent conflict between the two versions the owner already chose between
at capture is settled by that answer, never asked again (SR-077 EX-11, EX-12).

One test per entry point that meets the conflict: the record merge driver with git's
pre-merge-commit hook (the quick merge check), ``plumb merge-check`` and /plumb conflicts
(the card), and the owner's pick on the merge-time card, which answers an early decision
still waiting so the merge check never asks it a second time."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import pytest
from mergedriver.mdhelpers import (
    commit_all,
    install_driver,
    make_repo,
    parse,
    run_git,
)

from awareness.scenario import capture
from plumb import cli
from plumb.api import open_core

pytestmark = [pytest.mark.sr("SR-081"), pytest.mark.sr("SR-077")]
SR = ".plumb/requirements/SR-005.md"
OURS = "A relay pins only the records the owner's words affirm."
THEIRS = "A relay pins the stated group, named by its title."


def _write(root: Path, record_id: str, title: str, **fields: Any) -> None:
    from awareness.gitrepo import write_record

    write_record(root, record_id, title, **fields)


def _lanes(tmp_path: Path) -> tuple[Path, Path]:
    """main and worktree feat-x, the driver and the quick merge check installed; feat-x
    captures its version of SR-005 (its claim), then main captures another: the early
    conflict is raised on main."""
    from plumb.boundary.premerge import install_hook

    main = make_repo(tmp_path / "main")
    install_driver(main)
    install_hook(main, sys.executable)
    _write(main, "FEAT-002", "intent capture", description="capture")
    _write(main, "INT-001", "relay intent", quote="relay", readback="relay")
    _write(main, "SR-005", "relay checks", feature="FEAT-002",
           statement="A relay pins every stated record.")
    commit_all(main, "records")
    other = tmp_path / "wt-x"
    run_git(main, "worktree", "add", "-q", "-b", "feat-x", str(other))
    capture(other, {"intent": "INT-001", "updates": [{"id": "SR-005", "statement": THEIRS}]})
    capture(main, {"intent": "INT-001", "updates": [{"id": "SR-005", "statement": OURS}]})
    return main, other


def _decision(root: Path) -> Any:
    [dec] = [r for r in open_core(root).index().values() if r.kind == "decision"]
    return dec


def _commit_lanes(main: Path, other: Path) -> None:
    from plumb.approvals import approve

    approve(open_core(other), ["SR-005"])
    commit_all(other, "feat-x's relay\n\nSR: SR-005")
    commit_all(main, "main's relay\n\nSR: SR-005")


def _answered(tmp_path: Path, take: str) -> tuple[Path, Path, str]:
    main, other = _lanes(tmp_path)
    dec = _decision(main)
    assert cli.main(["conflict", "choose", dec.id, "--take", take, "--root", str(main)]) == 0
    from plumb.approvals import approve

    approve(open_core(main), ["INT-001", "SR-005"])
    _commit_lanes(main, other)
    return main, other, dec.id


def test_merge_hook_applies_the_earlier_answer(tmp_path: Path) -> None:
    """git merge: the quick check settles SR-005 with the owner's answer (feat-x's
    version) and stages it; git wrote the commit's tree before the hook, so the merge is
    held once and "finish the merge" records the answer. Nothing is asked again."""
    from plumb.boundary.premerge import check

    main, _other, dec = _answered(tmp_path, "feat-x")
    merged = run_git(main, "merge", "--no-edit", "feat-x", check=False)
    output = merged.stdout + merged.stderr
    assert merged.returncode != 0, output
    assert "as you answered before work began" in output
    assert 'say "finish the merge"' in output
    assert "Conflict  IC-" not in output and "Say:" not in output
    resolutions = [e.payload for e in open_core(main).log_read("events",
                                                               ["conflict-resolution"])]
    assert [(r["by"], r["decision"]) for r in resolutions] == [("owner-decision", dec)]
    assert run_git(main, "diff", "--name-only", "--", ".plumb").stdout == ""  # all staged
    assert check(open_core(main), "merge").exit == 0                # "finish the merge"
    run_git(main, "commit", "-q", "--no-edit")
    data = parse(run_git(main, "show", f"HEAD:{SR}").stdout)[0]
    assert data["statement"] == THEIRS and "conflict" not in data


def test_merge_card_and_conflicts_show_the_earlier_answer(tmp_path: Path) -> None:
    """Without the hook (``--no-verify``): the card says it is already answered, and
    /plumb conflicts settles it."""
    main, _other, _dec = _answered(tmp_path, "main")
    run_git(main, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-x", check=False)
    from plumb.mergedriver.conflicts import conflict_card, open_conflicts

    core = open_core(main)
    [conflict] = open_conflicts(core)
    card = "\n".join(conflict_card(core, conflict))
    assert "Already answered by you before work began: main's version" in card
    assert "Say:" not in card
    out = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(out):
        assert cli.main(["conflicts", "--root", str(main)]) == 0
    assert "now holds main's version, as you answered before work began" in out.getvalue()
    assert open_conflicts(open_core(main)) == ()
    assert parse((main / SR).read_text(encoding="utf-8"))[0]["statement"] == OURS


def test_merge_check_lists_no_answered_question(tmp_path: Path) -> None:
    from plumb.boundary.premerge import check

    main, _other, dec = _answered(tmp_path, "feat-x")
    run_git(main, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-x", check=False)
    report = check(open_core(main), "merge")
    assert report.intent_conflicts == ()
    assert dec not in [r["id"] for r in report.unconfirmed]
    assert any("as you answered before work began" in line for line in report.lines)


def test_merge_card_answer_answers_the_waiting_decision(tmp_path: Path) -> None:
    """The early decision was never answered: the merge-time card is the one question
    (the merge check does not list the decision beside it), and its answer answers the
    decision too."""
    from plumb.boundary.premerge import check
    main, other = _lanes(tmp_path)
    dec = _decision(main).id
    from plumb.approvals import approve

    approve(open_core(main), ["INT-001", "SR-005"])
    _commit_lanes(main, other)
    run_git(main, "merge", "--no-edit", "--no-verify", "--no-commit", "feat-x", check=False)
    report = check(open_core(main), "merge")
    assert [c["record"] for c in report.intent_conflicts] == ["SR-005"]
    assert dec not in [r["id"] for r in report.unconfirmed]
    assert cli.main(["conflict", "choose", "IC-001", "--take", "feat-x",
                     "--root", str(main)]) == 0
    core = open_core(main)
    assert core.index()[dec].fields["chosen"] == "feat-x's version"
    assert core.status([dec])[dec].confirmation == "confirmed"
