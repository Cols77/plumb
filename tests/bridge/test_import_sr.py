"""BRIDGE BS2: importing pi-agent-factory requirements (spec 8.1)."""

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


def _kinds(findings, kind):
    return [f for f in findings if f["kind"] == kind]


def test_imports_sr_fields_and_ac_examples(repo: Path, pi_source: Path) -> None:
    report = import_pi_factory(open_core(repo), pi_source, only={"SR"})
    record = open_core(repo).index()["SR-077"]
    assert record.kind == "requirement"
    assert record.title.startswith("Typed judgment adapter")
    assert record.fields["statement"].startswith("The system shall obtain typed judgments")
    assert record.fields["domain"] == "behavioral"
    assert [e.id for e in record.examples] == ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5", "AC-6"]
    assert record.examples[1].criterion.startswith("Every judgment records")
    assert "Implemented by" in record.body
    assert report["counts"]["requirement"] == 3


def test_structured_bindings_become_links_pinned_when_ends_exist(repo: Path,
                                                                 pi_source: Path) -> None:
    model = repo / "src" / "substrate" / "judgment" / "model.py"
    model.parent.mkdir(parents=True)
    model.write_text("class JudgmentRecord: ...\n", encoding="utf-8")
    test = repo / "tests" / "unit" / "substrate" / "judgment" / "test_evidence_record.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_x(): pass\n", encoding="utf-8")
    import_pi_factory(open_core(repo), pi_source, only={"SR"})
    core = open_core(repo)
    states = core.link_states(["SR-077"])
    by_path = {(s.link.kind, s.link.target.path, s.link.example): s for s in states}
    impl = by_path[("implemented_by", "src/substrate/judgment/model.py", None)]
    assert impl.state == "current"
    ver = by_path[("verified_by", "tests/unit/substrate/judgment/test_evidence_record.py",
                   None)]
    assert ver.state == "current"
    # an acceptance criterion's test_marker ref becomes a verified_by link for its example
    ac = by_path[("verified_by", "tests/unit/substrate/judgment/test_evidence_record.py",
                  "AC-2")]
    assert ac.state == "current"
    assert all(s.state == "current" for s in states)


def test_missing_ends_reported_as_findings(repo: Path, pi_source: Path) -> None:
    report = import_pi_factory(open_core(repo), pi_source, only={"SR"})
    missing = _kinds(report["findings"], "missing-end")
    assert any(f["id"] == "SR-077" and "src/substrate/judgment/tiers.py" in f["detail"]
               for f in missing)
    # no dangling link is ever written
    assert all(s.state != "dangling" for s in open_core(repo).link_states())


def test_legacy_checksum_verified_and_reported(repo: Path, pi_source: Path) -> None:
    report = import_pi_factory(open_core(repo), pi_source, only={"SR"}, dry_run=True)
    assert any(f["id"] == "SR-003" and f["kind"] == "checksum-ok"
               for f in report["findings"])
    path = pi_source / "requirements" / "SR-003.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "failing deterministically", "failing quietly"), encoding="utf-8")
    report = import_pi_factory(open_core(repo), pi_source, only={"SR"}, dry_run=True)
    assert any(f["id"] == "SR-003" and f["kind"] == "checksum-mismatch"
               for f in report["findings"])


def test_all_imported_records_are_proposed(repo: Path, pi_source: Path) -> None:
    # every record is proposed, except where an upstream human consent pins the current
    # content (SR-059, next-plan 9.3): those are confirmed by import, nothing else
    import_pi_factory(open_core(repo), pi_source)
    core = open_core(repo)
    statuses = core.status()
    confirmed = {rid for rid, s in statuses.items() if s.confirmation != "proposed"}
    assert confirmed == {"SR-077", "SR-078"}
    assert all(statuses[rid].approved_by == "import" for rid in confirmed)
    assert [e.kind for e in core.log_read("events")] == ["import", "approval"]


def test_upstream_links_resolve_within_the_batch(repo: Path, pi_source: Path) -> None:
    path = pi_source / "requirements" / "SR-077.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "upstream: []", "upstream: [SR-003, SR-404]"), encoding="utf-8")
    report = import_pi_factory(open_core(repo), pi_source, only={"SR"})
    states = open_core(repo).link_states(["SR-077"])
    upstream = [s for s in states if s.link.kind == "upstream"]
    assert [(s.link.target.record, s.state) for s in upstream] == [("SR-003", "current")]
    assert any(f["kind"] == "missing-end" and "SR-404" in f["detail"]
               for f in report["findings"])
