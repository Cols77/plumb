"""I4: relations become symbol, test-node, record and path links (next-plan 9.1, 9.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from importer_helpers import make_source, rewrite, write

from plumb.api import open_core
from plumb.contracts import Target
from plumb.importer.pi_factory import import_pi_factory

pytestmark = pytest.mark.sr("SR-058")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_source(tmp_path)


def _targets(core, record_id: str) -> dict[tuple[str, Target, str | None], str]:
    return {(s.link.kind, s.link.target, s.link.example): s.state
            for s in core.link_states([record_id])}


def test_bindings_become_symbol_and_node_links(repo: Path, source: Path) -> None:
    model = write(repo, "src/substrate/judgment/model.py",
                  "class JudgmentRecord:\n    size = 1\n\n\ndef helper():\n    return 0\n")
    write(repo, "src/substrate/judgment/__init__.py", "from .model import JudgmentRecord\n")
    write(repo, "tests/unit/substrate/judgment/test_evidence_record.py",
          "def test_digest():\n    assert True\n")
    sr = source / "requirements" / "SR-077.md"
    rewrite(sr, 'ref: "tests/unit/substrate/judgment/test_evidence_record.py"',
            'ref: "tests/unit/substrate/judgment/test_evidence_record.py::test_digest[x]"')
    report = import_pi_factory(open_core(repo), source, only={"SR"})
    core = open_core(repo)
    links = _targets(core, "SR-077")
    symbol = Target(path="src/substrate/judgment/model.py",
                    symbol="substrate.judgment.model:JudgmentRecord")
    assert links[("implemented_by", symbol, None)] == "current"
    node = Target(test="tests/unit/substrate/judgment/test_evidence_record.py::test_digest")
    assert links[("verified_by", node, "AC-2")] == "current"
    # a symbol the file does not define (a re-export) is linked as the whole file, reported
    assert links[("implemented_by", Target(path="src/substrate/judgment/__init__.py"),
                  None)] == "current"
    assert any(f["kind"] == "symbol-narrowed" and "open_judgment_client" in f["detail"]
               for f in report["findings"])
    # an edit elsewhere in the file leaves the symbol link current (SR-058 EX-1)
    rewrite(model, "return 0", "return 1")
    assert _targets(open_core(repo), "SR-077")[("implemented_by", symbol, None)] == "current"
    rewrite(model, "size = 1", "size = 2")
    assert _targets(open_core(repo), "SR-077")[("implemented_by", symbol, None)] == "stale"


def test_spec_relation_becomes_relates_to_path(repo: Path, source: Path) -> None:
    spec = "docs/coherence/specs/2026-10-04-safe-integration.md"
    text = "---\nid: SPEC-SAFE-INTEGRATION\ntitle: Safe integration\nstatus: draft\n---\nBody\n"
    write(source, spec, text)
    rewrite(source / "requirements" / "SR-003.md", "upstream: []",
            "upstream: []\nrelates_to:\n- spec:SPEC-SAFE-INTEGRATION\n- spec:SPEC-NOWHERE")
    report = import_pi_factory(open_core(repo), source, only={"SR"})
    assert ("relates_to", Target(path=spec), None) not in _targets(open_core(repo), "SR-003")
    assert any(f["kind"] == "relation-skipped" and "SPEC-SAFE-INTEGRATION" in f["detail"]
               and spec in f["detail"] for f in report["findings"])
    assert any(f["kind"] == "relation-skipped" and "SPEC-NOWHERE" in f["detail"]
               for f in report["findings"])
    # once the document exists in the target, the relation is a relates_to path link
    write(repo, spec, text)
    import_pi_factory(open_core(repo), source, only={"SR"})
    assert _targets(open_core(repo), "SR-003")[("relates_to", Target(path=spec), None)] == \
        "current"
    from plumb.validate import validate

    assert not [f for f in validate(open_core(repo)) if f.code == "kind"]


def test_feature_union_and_differences(repo: Path, source: Path) -> None:
    rewrite(source / "bundles" / "FEAT-001.json", '"sr:SR-001"', '"sr:SR-001", "sr:SR-099"')
    report = import_pi_factory(open_core(repo), source)
    feature = open_core(repo).index()["FEAT-001"]
    members = feature.fields["requirements"]
    assert {"SR-050", "SR-064", "SR-099", "SR-003"} <= set(members)
    assert len(members) == len(set(members))
    [diff] = [f for f in report["findings"] if f["kind"] == "membership-difference"]
    assert "SR-050" in diff["detail"] and "SR-099" in diff["detail"]
    assert open_core(repo).index()["SR-003"].fields["feature"] == "FEAT-001"


def test_nc_corrects_link(repo: Path, source: Path) -> None:
    nc = source / "docs" / "nonconformances" / "NC-0002-empty-planning-brief.md"
    rewrite(nc, "## Symptom", "Against SR-003 and SR-404.\n\n## Symptom")
    report = import_pi_factory(open_core(repo), source)
    links = _targets(open_core(repo), "NC-0002")
    assert links == {("corrects", Target(record="SR-003"), None): "current"}
    assert any(f["kind"] == "missing-end" and f["id"] == "NC-0002" and "SR-404" in f["detail"]
               for f in report["findings"])
