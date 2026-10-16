"""PS2: plumb align judges each edge, weakest first, and never changes one (R12.2, sp5 8,
SR-067)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import FEAT1, INT1, SR1, SR2, FakeBackend, write_all

from plumb import cli
from plumb.align import align, align_lines, collect
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-246")


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, INT1, FEAT1)
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef divide(a, b):\n    return a / b\n",
        "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_add():\n    assert 1 + 2 == 3\n",
                                                 "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/app/calc.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_calc.py"), "EX-1")
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    core.add_link("SR-002", "implemented_by", Target(path="src/app/calc.py"))
    core.add_link("SR-002", "verified_by", Target(path="tests/test_calc.py"), "EX-1")
    return repo


def _link_states(repo: Path) -> list:
    core = open_core(repo)
    return [(s.link.id, s.state) for s in core.link_states()]


def test_gaps_named(records: Path) -> None:
    """EX-1: an example linked to no test is a named gap."""
    result = align(open_core(records), ["SR-002"], backend=None, use_cache=False)
    assert "SR-002/EX-2 has no test" in result.gaps
    assert "SR-001 derives from no intent" not in result.gaps  # out of scope
    lines = align_lines(result)
    assert "gap: SR-002/EX-2 has no test" in lines


def test_collection_fingerprint_deterministic(records: Path) -> None:
    core = open_core(records)
    first = collect(core, ["SR-001", "SR-002"])
    again = collect(open_core(records), ["SR-002", "SR-001"])
    assert first == again
    a = align(core, ["SR-001", "SR-002"], backend=FakeBackend(), use_cache=False)
    b = align(open_core(records), ["SR-002", "SR-001"], backend=FakeBackend(),
              use_cache=False)
    assert a.fingerprint == b.fingerprint
    assert ("INT-001", "SR-002") in {(e.source, e.target) for e in a.edges}
    assert ("SR-002/EX-1", "tests/test_calc.py") in {(e.source, e.target) for e in a.edges}


def test_judgments_never_change_edges(records: Path) -> None:
    """EX-2: a backend answering no for the SR-002 -> code edge lists it first; every link
    state and record file is unchanged."""
    before = _link_states(records)
    files = {p: p.read_bytes() for p in (records / ".plumb").rglob("*.md")}
    backend = FakeBackend(answers={"SR-002->src/app/calc.py": "no"})
    result = align(open_core(records), ["SR-002"], backend=backend, use_cache=False)
    assert (result.edges[0].source, result.edges[0].target) == ("SR-002", "src/app/calc.py")
    assert result.edges[0].verdict == "no"
    assert result.edges[0].question == "Does this code realize this requirement?"
    assert _link_states(records) == before
    assert {p: p.read_bytes() for p in (records / ".plumb").rglob("*.md")} == files


def test_no_judge_reports_only_gaps_and_says_why(records: Path, capsys) -> None:
    """INT-029: no judge configured: edges listed unjudged, no term-overlap score."""
    assert cli.main(["align", "--root", str(records), "--json", "SR-002"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["backend"] == "none" and not data["available"]
    assert "judgment.backend" in data["unavailable"]
    assert all(e["verdict"] == "unjudged" and e["score"] is None for e in data["edges"])
    assert cli.main(["align", "--root", str(records), "SR-002"]) == 0
    assert "judging unavailable: no judge" in capsys.readouterr().out
    (records / ".plumb" / "config.yaml").write_text("judgment:\n  backend: disabled\n",
                                                    "utf-8")
    assert cli.main(["align", "--root", str(records), "the", "divide", "quotient"]) == 0
    out = capsys.readouterr().out
    assert "judging unavailable: judgment.backend is disabled" in out
    assert "gap: SR-002/EX-2 has no test" in out
