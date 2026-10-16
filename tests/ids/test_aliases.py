"""IDS I6: approvals and trailers carried across a renumber (sp6 5.4, 5.5; R17; SR-071).

An "ok" carries over only while the words are byte-identical, and it is labelled "carried by
renumber SR-002 -> SR-003" in /plumb show and the merge-boundary glance."""

from __future__ import annotations

from pathlib import Path

import pytest

from ids import scenario
from ids.gitrepo import commit_all, run_git
from plumb import ids
from plumb.api import open_core
from plumb.capture.records import record_fields
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-257")


def _fixed(tmp_path: Path, **kwargs) -> tuple[scenario.Scenario, str]:
    s = scenario.build(tmp_path, **kwargs)
    result = ids.merge_fix(open_core(s.origin))
    return s, result.renumbered[0]["to"]


def test_approval_carried_for_pure_renumber(tmp_path: Path, capsys) -> None:
    s, new = _fixed(tmp_path)
    status = open_core(s.origin).status([new])[new]
    assert status.confirmation == "confirmed" and status.approved_by == "owner"
    assert status.carried_from == "SR-002"
    # our own SR-002 was never approved: nothing leaks to it
    assert open_core(s.origin).status(["SR-002"])["SR-002"].confirmation == "proposed"
    assert main(["show", new, "--root", str(s.origin)]) == 0
    out = capsys.readouterr().out
    assert f"confirmed by you, carried by renumber SR-002 -> {new}" in out


def test_carried_label_in_the_merge_glance(tmp_path: Path) -> None:
    from plumb.boundary.glance import glance_line, glance_rows

    s, new = _fixed(tmp_path)
    rows = [r for r in glance_rows(open_core(s.origin), set()) if r["kind"] == "renumber"]
    assert len(rows) == 1
    line = glance_line(rows[0])
    assert f"carried by renumber SR-002 -> {new}" in line and "export csv" in line


def test_approval_not_carried_after_an_edit(tmp_path: Path) -> None:
    s, new = _fixed(tmp_path)
    core = open_core(s.origin)
    record = core.index()[new]
    core.write_record("requirement", {**record_fields(record), "statement": "tsv now"},
                      record.body, record_id=new)
    status = open_core(s.origin).status([new])[new]
    assert status.confirmation != "confirmed" and status.carried_from is None


def test_approval_of_other_content_not_carried(tmp_path: Path) -> None:
    s = scenario.build(tmp_path, merge=False)
    core = open_core(s.clone)  # the clone's owner approved an earlier wording
    record = core.index()["SR-002"]
    core.write_record("requirement", {**record_fields(record), "statement": "rows as csv"},
                      record.body, record_id="SR-002")
    commit_all(s.clone, "reword\n\nSR: SR-002")
    run_git(s.origin, "fetch", "-q", str(s.clone), "main:incoming")
    run_git(s.origin, "merge", "--no-edit", "incoming", check=False)
    result = ids.merge_fix(open_core(s.origin))
    new = result.renumbered[0]["to"]
    assert result.renumbered[0]["approvals"] == []
    assert "no approval to carry" in result.lines[0]
    assert open_core(s.origin).status([new])[new].confirmation == "proposed"


def test_revoking_the_new_id_drops_the_carry(tmp_path: Path) -> None:
    from plumb import approvals

    s, new = _fixed(tmp_path)
    approvals.revoke(open_core(s.origin), [new])
    assert open_core(s.origin).status([new])[new].confirmation != "confirmed"


def test_claims_reads_incoming_trailers_as_new_id(tmp_path: Path) -> None:
    from plumb.claims import claims_check

    s, new = _fixed(tmp_path)
    fork = run_git(s.origin, "merge-base", "HEAD", "incoming").strip()
    run_git(s.origin, "commit", "-q", "--no-edit", "--no-verify")
    result = claims_check(s.origin, f"{fork}..HEAD")
    assert result["undeclared"] == [], result
    # history is unchanged: the commits still say SR-002
    assert "SR: SR-002" in run_git(s.origin, "log", "-1", "--format=%B", s.clone_commits[1])


def test_claims_without_the_map_would_misread(tmp_path: Path, monkeypatch) -> None:
    from plumb import claims

    s, _ = _fixed(tmp_path)
    fork = run_git(s.origin, "merge-base", "HEAD", "incoming").strip()
    run_git(s.origin, "commit", "-q", "--no-edit", "--no-verify")
    monkeypatch.setattr(claims, "_trailer_aliases", lambda core: {})
    paths = {row["path"] for row in claims.claims_check(s.origin, f"{fork}..HEAD")["undeclared"]}
    assert "tests/test_export.py" in paths


def test_validate_rejects_forged_renumber(tmp_path: Path) -> None:
    from plumb.validate import validate

    s, new = _fixed(tmp_path)
    core = open_core(s.origin)
    # a forged entry: carry the clone owner's approval onto our own "relay checks"
    real = [e for e in core.events() if e.kind == "renumber"][0].payload
    core.log_append("events", "renumber", {
        **real, "from": "SR-002", "to": "SR-002", "new_hash": core.index()["SR-002"].hash,
        "map": {"SR-002": "SR-002"}})
    core.log_append("events", "renumber", {**real, "approvals": ["sha256:" + "0" * 64]})
    core = open_core(s.origin)
    errors = [f for f in validate(core) if f.code == "renumber"]
    assert any("does not exist" in f.message for f in errors)
    assert any("not SR-002's" in f.message for f in errors)
    assert core.status(["SR-002"])["SR-002"].confirmation == "proposed"
