"""BRIDGE BS2: features with bundles, nonconformances and collisions (spec 8.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pi_source_fixture import make_pi_source

from plumb.api import open_core
from plumb.importer.pi_factory import import_pi_factory

pytestmark = pytest.mark.sr("SR-238")


@pytest.fixture
def pi_source(tmp_path: Path) -> Path:
    return make_pi_source(tmp_path)


def test_feature_membership_is_union_of_feat_and_bundle(repo: Path, pi_source: Path) -> None:
    bundle = pi_source / "bundles" / "FEAT-001.json"
    bundle.write_text(bundle.read_text(encoding="utf-8").replace(
        '"sr:SR-001"', '"sr:SR-001", "sr:SR-099", "task:T-001"'), encoding="utf-8")
    import_pi_factory(open_core(repo), pi_source, only={"FEAT"})
    feature = open_core(repo).index()["FEAT-001"]
    assert feature.kind == "feature"
    assert feature.title == "REQ-TRACEABILITY"
    members = feature.fields["requirements"]
    assert members[:3] == ["SR-002", "SR-003", "SR-004"]
    assert {"SR-050", "SR-064", "SR-099"} <= set(members)
    assert "T-001" not in members and len(members) == len(set(members))


def test_membership_differences_reported(repo: Path, pi_source: Path) -> None:
    report = import_pi_factory(open_core(repo), pi_source, only={"FEAT"}, dry_run=True)
    diffs = [f for f in report["findings"] if f["kind"] == "membership-difference"]
    detail = " ".join(f["detail"] for f in diffs)
    assert "SR-050" in detail and "SR-064" in detail


def test_requirement_feature_set_from_membership(repo: Path, pi_source: Path) -> None:
    import_pi_factory(open_core(repo), pi_source)
    assert open_core(repo).index()["SR-003"].fields["feature"] == "FEAT-001"


def test_nc_read_leniently_keeps_corrected_by(repo: Path, pi_source: Path) -> None:
    broken = pi_source / "docs" / "nonconformances" / "NC-0042-no-frontmatter.md"
    broken.write_text("# Something went wrong\n\nNo frontmatter here.\n", encoding="utf-8")
    report = import_pi_factory(open_core(repo), pi_source, only={"NC"})
    index = open_core(repo).index()
    nc = index["NC-0002"]
    assert nc.kind == "nc"
    assert nc.fields["status"] == "corrected"
    assert nc.fields["corrected_by"] == "T-106"
    assert nc.fields["detected_by"] == "FEAT-018 intent-review-agent"
    assert "## Symptom" in nc.body
    lenient = index["NC-0042"]
    assert lenient.title == "Something went wrong"
    assert lenient.fields["status"] == "open"
    assert any(f["id"] == "NC-0042" and f["kind"] == "lenient" for f in report["findings"])


def test_id_collision_skipped_with_finding(repo: Path, pi_source: Path, write_record) -> None:
    mine = write_record(repo, "---\nid: SR-003\ntitle: Mine\nstatement: plumb's own.\n---\n")
    report = import_pi_factory(open_core(repo), pi_source, only={"SR"})
    assert any(f["id"] == "SR-003" and f["kind"] == "collision" for f in report["findings"])
    assert open_core(repo).index()["SR-003"].title == "Mine"
    assert mine.read_text(encoding="utf-8").startswith("---\nid: SR-003\ntitle: Mine")
    assert "SR-077" in open_core(repo).index()
