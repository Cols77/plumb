"""P4: the owner's words resolve to records, paths and tests (sp5 5, SR-064)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import FEAT1, FEAT2, INT1, SR1, SR2, SR3, write_all

from plumb import cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.present.resolve import resolve

pytestmark = pytest.mark.sr("SR-064")

SR4 = """---
id: SR-004
title: customers export to json
feature: FEAT-002
statement: A customer list exports to one json file.
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, SR3, SR4, INT1, FEAT1, FEAT2)
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                                  "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_add():\n    pass\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/app/calc.py"))
    core.add_link("SR-001", "verified_by", Target(test="tests/test_calc.py::test_add"),
                  "EX-1")
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo


def test_ids_and_paths_first(records: Path) -> None:
    core = open_core(records)
    by_id = resolve(core, "what about SR-002 and the export")
    assert by_id.how == "id" and by_id.ids == ("SR-002",)
    by_path = resolve(core, "src/app/calc.py")
    assert by_path.how == "path" and by_path.ids == ("SR-001",)
    by_test = resolve(core, "tests/test_calc.py::test_add")
    assert by_test.how == "test" and by_test.ids == ("SR-001",)


def test_plain_words_pick_the_title_match_with_its_reason(records: Path) -> None:
    resolution = resolve(open_core(records), "how numbers are added")
    assert not resolution.ambiguous
    assert resolution.ids[0] == "SR-001"
    assert resolution.items[0].reason == "matched the title of SR-001"


def test_ambiguous_lists_candidates(records: Path, capsys) -> None:
    """EX-2: two records match "the export" equally: both listed, none chosen."""
    resolution = resolve(open_core(records), "the export")
    assert resolution.ambiguous and resolution.ids == ()
    assert {i.ref for i in resolution.items} >= {"SR-003", "SR-004"}
    assert cli.main(["resolve", "--root", str(records), "the", "export"]) == 0
    out = capsys.readouterr().out
    assert '"the export" could mean:' in out
    assert 'SR-003 "invoices export to csv"' in out and 'SR-004 "customers export to json"' \
        in out
    assert "which one do you mean?" in out


def test_a_chain_is_one_answer(records: Path) -> None:
    """A requirement and the intent it derives from are not two competing answers."""
    resolution = resolve(open_core(records), "multiply next to add divide")
    assert not resolution.ambiguous


def test_explain_takes_plain_words(records: Path, capsys) -> None:
    """EX-1: plumb explain how numbers are added explains SR-001 with its examples."""
    assert cli.main(["explain", "--root", str(records), "how", "numbers", "are",
                     "added"]) == 0
    out = capsys.readouterr().out
    assert 'SR-001 "add returns the sum of two numbers"' in out
    assert "example EX-1: given a = 1 and b = 2, when add(a, b) is called, then it returns 3" \
        in out
    assert cli.main(["explain", "--root", str(records), "--json", "the", "export"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["records"] == [] and set(data["candidates"]) >= {"SR-003", "SR-004"}


def test_show_and_impact_take_plain_words(records: Path, capsys) -> None:
    assert cli.main(["show", "--root", str(records), "divide", "quotient"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("SR-002 (requirement, proposed)")
    assert cli.main(["show", "--root", str(records), "SR-001"]) == 0
    assert capsys.readouterr().out.startswith("SR-001 (requirement")
    assert cli.main(["show", "--root", str(records), "the", "export"]) == 0
    assert "which one do you mean?" in capsys.readouterr().out
    assert cli.main(["impact", "--root", str(records), "how", "numbers", "are",
                     "added"]) == 0
    assert "SR-001" in capsys.readouterr().out
