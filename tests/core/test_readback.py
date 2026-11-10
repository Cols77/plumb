"""The read-back rendering shared by the stop summary and ``iaso show`` (spec 6.4, R1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso import cli
from iaso.api import open_core
from iaso.readback import record_lines

pytestmark = pytest.mark.sr("SR-265")

INT = """---
id: INT-001
title: Divide numbers
quote: add a divide function
readback: You want a divide function for two numbers.
will:
- id: W-1
  text: add divide(a, b)
wont:
- handle complex numbers
assumptions:
- id: A-1
  text: division by zero raises ValueError
---
"""
SR = """---
id: SR-002
title: Divide
statement: divide returns a / b.
examples:
- id: EX-1
  given: 6 and 3
  when: divide runs
  then: it returns 2
- id: EX-2
  given: 1 and 0
  when: divide runs
  then: it returns 0
- id: AC-1
  criterion: imported acceptance text
---
"""
DEC = """---
id: DEC-001
title: Division kind
chosen: integer floor division
alternatives:
- true float division
matters: true
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    for text in (INT, SR, DEC):
        write_record(repo, text)
    return repo


def test_intent_shows_readback_will_wont_and_labelled_assumptions(records: Path) -> None:
    lines = record_lines(open_core(records).index()["INT-001"])
    assert lines == [
        "INT-001: You want a divide function for two numbers.",
        "INT-001 will: add divide(a, b)",
        "INT-001 won't: handle complex numbers",
        "INT-001/A-1 assumption: division by zero raises ValueError",
    ]


def test_requirement_shows_statement_and_every_example(records: Path) -> None:
    lines = record_lines(open_core(records).index()["SR-002"])
    assert lines == [
        "SR-002: divide returns a / b.",
        "SR-002/EX-1: given 6 and 3, when divide runs, then it returns 2",
        "SR-002/EX-2: given 1 and 0, when divide runs, then it returns 0",
        "SR-002/AC-1: imported acceptance text",
    ]


def test_decision_shows_chosen_and_alternatives(records: Path) -> None:
    lines = record_lines(open_core(records).index()["DEC-001"])
    assert lines == ["DEC-001: Division kind: integer floor division",
                     "DEC-001 alternatives: true float division"]


def test_show_prints_full_content_and_confirmation(records: Path,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "SR-002", "INT-001", "--root", str(records)]) == 0
    out = capsys.readouterr().out
    assert "SR-002 (requirement, proposed) .iaso/requirements/SR-002.md" in out
    assert "SR-002/EX-2: given 1 and 0, when divide runs, then it returns 0" in out
    assert "INT-001/A-1 assumption: division by zero raises ValueError" in out


def test_show_unknown_record_is_a_finding(records: Path,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "SR-999", "--root", str(records)]) == 1
    assert "no record SR-999" in capsys.readouterr().err
