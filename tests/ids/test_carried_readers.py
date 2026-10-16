"""IDS: an approval a renumber carried counts in every reader of approvals and trailers at
the merge boundary (sp6 5.4, 5.5; R17; SR-071).

The confirmation states read through ``confirm.carry_renumbers``; what an approval pinned
(its owning ends, a set approval's members) reads through
``confirm.pinned_through_renumbers``; a past commit's ``SR:`` trailer reads through
``claims.claimed_ids``. One test per reader: after a pure renumber the merge report holds
nothing the owner already said "ok" to."""

from __future__ import annotations

from pathlib import Path

import pytest

from ids.gitrepo import clone, commit_all, make_repo, run_git
from plumb import approvals, ids
from plumb.api import open_core
from plumb.boundary import merge_report
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-257")


def _requirement(root: Path, title: str, source: str) -> str:
    core = open_core(root)
    record = core.write_record("requirement", {"title": title, "statement": title}, "")
    core.add_link(record.id, "derives_from", Target(record="INT-001"))
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / source).write_text("X = 1\n", encoding="utf-8")
    core.add_link(record.id, "implemented_by", Target(path=f"src/{source}"))
    return record.id


def _renumbered(tmp_path: Path, *, escalated: bool = False) -> Path:
    """The clone's owner approves its SR-001 "export csv" (with its owning end; with
    ``escalated``, as the one member of the escalated set INT-002); origin adds its own,
    unapproved SR-001 "relay checks"; origin merges, ``merge-fix`` renumbers the incoming
    record to SR-002, and the merge is committed."""
    origin = make_repo(tmp_path / "origin")
    core = open_core(origin)
    core.write_record("intent", {"title": "csv and relays", "quote": "q", "readback": "r"},
                      "")
    approvals.approve(open_core(origin), ["INT-001"])
    commit_all(origin, "base")

    other = clone(origin, tmp_path / "clone")
    sr = _requirement(other, "export csv", "export.py")
    approve = [sr]
    if escalated:
        anchor = open_core(other).write_record("intent", {
            "title": "export spec", "quote": "q", "readback": "r", "mode": "escalated",
            "members": [sr]}, "")
        approve.append(anchor.id)
    approvals.approve(open_core(other), approve)
    commit_all(other, f"export csv\n\nSR: {sr}")

    assert _requirement(origin, "relay checks", "relay.py") == sr
    commit_all(origin, f"relay checks\n\nSR: {sr}")

    run_git(origin, "fetch", "-q", str(other), "main:incoming")
    assert "CONFLICT" in run_git(origin, "merge", "--no-edit", "incoming", check=False)
    result = ids.merge_fix(open_core(origin))
    assert [r["to"] for r in result.renumbered] == ["SR-002"], result.lines
    assert result.renumbered[0]["approvals"]
    run_git(origin, "commit", "-q", "--no-edit", "--no-verify")
    return origin


def _report(origin: Path):
    report = merge_report(open_core(origin), "HEAD^1", run_full=False)
    assert report.error is None or report.error == "", report.error
    return report


def test_carried_approval_covers_the_owning_ends(tmp_path: Path) -> None:
    from plumb.merge import approved_ends

    origin = _renumbered(tmp_path)
    core = open_core(origin)
    assert core.status(["SR-002"])["SR-002"].carried_from == "SR-001"
    assert approved_ends(core).get("SR-002") == {"implemented_by src/export.py"}
    report = _report(origin)
    assert "SR-002" in report.touched
    assert report.awaiting == (), report.awaiting
    assert report.exit == 0, report


def test_incoming_trailers_name_the_renumbered_record(tmp_path: Path) -> None:
    origin = _renumbered(tmp_path)
    # origin's own SR-001 is unapproved and untouched by the incoming commits, whose
    # "SR: SR-001" now means SR-002
    assert open_core(origin).status(["SR-001"])["SR-001"].confirmation == "proposed"
    report = _report(origin)
    assert report.touched == ("SR-002",)
    assert report.exit == 0, report


def test_carried_approval_confirms_the_escalated_set(tmp_path: Path) -> None:
    from plumb.boundary.report import _set_confirmed

    origin = _renumbered(tmp_path, escalated=True)
    core = open_core(origin)
    anchor = next(r for r in core.index().values() if r.fields.get("mode") == "escalated")
    assert anchor.fields["members"] == ["SR-002"]
    assert _set_confirmed(core, ["SR-002"])
    report = _report(origin)
    assert report.awaiting == (), report.awaiting
    assert report.exit == 0, report
