"""CAPTURE CS5: ownership proposals, "does this diff serve its claimed SRs?" and proposed
test nodes: proposals only, never a written link (R12.3; sp2 10.1, SR-044)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import record_text, tree_bytes

from plumb.api import open_core
from plumb.capture import api
from plumb.capture.ownership import diff_serves, node_proposals, ownership_proposals
from plumb.contracts import Target
from plumb.judgment import FakeBackend

pytestmark = pytest.mark.sr("SR-200")

EX = [{"id": "EX-1", "given": "a = 1 and b = 2", "when": "add runs",
       "then": "it returns the sum 3"}]


@pytest.fixture
def calc(repo: Path, write_record) -> Path:
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                                  encoding="utf-8")
    (repo / "src" / "app" / "mul.py").write_text("def mul(a, b):\n    return a * b\n",
                                                 encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text(
        "def test_add_returns_sum():\n    '''add returns the sum'''\n\n\n"
        "def test_module_imports():\n    pass\n", encoding="utf-8")
    write_record(repo, record_text("SR-001", "add returns the sum",
                                   statement="add(a, b) returns the sum", examples=EX))
    write_record(repo, record_text("SR-004", "reports list totals",
                                   statement="the report lists totals"))
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/app/calc.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_calc.py"), "EX-1")
    return repo


OWNER = FakeBackend({("ownership", "src/app/mul.py"): ("SR-001: add returns the sum", 0.9)})


def test_untraced_change_names_a_proposed_owner_and_writes_no_link(
        calc: Path, monkeypatch) -> None:
    import plumb.judgment

    monkeypatch.setattr(plumb.judgment, "get_backend", lambda core, hook: OWNER)
    before = tree_bytes(calc)
    proposals = ownership_proposals(open_core(calc), ["src/app/mul.py", "src/app/calc.py"])
    assert list(proposals) == ["src/app/mul.py"]  # calc.py is owned already
    proposal = proposals["src/app/mul.py"]
    assert proposal.proposed == "SR-001"
    assert proposal.line == ("plumb: src/app/mul.py: SR-001 may own this (proposed); read it "
                             "back and link it, or record a new SR")
    assert tree_bytes(calc) == before
    assert api.ownership_proposals(open_core(calc), ["src/app/mul.py"])["src/app/mul.py"] \
        .proposed == "SR-001"


def test_no_judge_names_the_candidates_and_the_cause(calc: Path) -> None:
    """INT-029: no rule-based owner is proposed when no judge can choose."""
    proposal = ownership_proposals(open_core(calc), ["src/app/mul.py"])["src/app/mul.py"]
    assert proposal.proposed is None and proposal.candidates == ("SR-001",)
    assert "judging unavailable" in proposal.line and "judgment.backend" in proposal.line


def test_no_clear_lead_reports_no_judgments(calc: Path, write_record) -> None:
    write_record(calc, record_text("SR-002", "sub returns the difference",
                                   statement="sub(a, b) returns the difference"))
    open_core(calc).add_link("SR-002", "implemented_by", Target(path="src/app/calc.py"))
    proposal = ownership_proposals(open_core(calc), ["src/app/mul.py"],
                                   backend=FakeBackend())["src/app/mul.py"]
    assert proposal.proposed is None and set(proposal.candidates) == {"SR-001", "SR-002"}
    assert "no judgments available" in proposal.line


def test_diff_not_serving_a_claimed_sr_warns(calc: Path) -> None:
    backend = FakeBackend({("ownership", "SR-004"): ("no", 0.95)})
    lines = diff_serves(open_core(calc), ["SR-004"], ["src/app/report.py"], backend=backend)
    assert lines == ["plumb: warning: SR-004 may not be served by src/app/report.py"]
    [unavailable] = diff_serves(open_core(calc), ["SR-004"], ["src/app/report.py"])
    assert unavailable.startswith("plumb: judging unavailable:")  # no judge, no rule
    sure = FakeBackend({("ownership", "SR-004"): ("yes", 0.95)})
    assert diff_serves(open_core(calc), ["SR-004"], ["src/app/report.py"], backend=sure) == []


def test_bare_test_file_gets_a_proposed_node(calc: Path, capsys) -> None:
    [proposal] = node_proposals(open_core(calc), ["SR-001"])
    assert proposal.proposed == "tests/test_calc.py::test_add_returns_sum"
    from plumb.cli import main

    before = tree_bytes(calc)
    main(["drift", "--root", str(calc)])
    out = capsys.readouterr().out
    assert ("plumb: hint: SR-001 EX-1 is verified by the whole file tests/test_calc.py; "
            "proposed node tests/test_calc.py::test_add_returns_sum (not written)") in out
    assert tree_bytes(calc) == before
