"""``plumb explain <anything>``: plain words, a path or an ID resolve to the records and their
upward chain in the owner's terms (ruling R9; ``why`` is an alias)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import cli
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-033")

INT = """---
id: INT-001
title: Totals are rounded for invoices
quote: "invoice totals should be rounded to the cent"
readback: Round invoice totals to two decimals.
---
"""
SR = """---
id: SR-001
title: Invoice totals are rounded to the cent
statement: total() rounds the invoice sum half-up to two decimals.
examples:
  - {id: EX-1, given: lines 0.105 and 0.2, when: totalled, then: the total is 0.31}
---
"""
SR2 = """---
id: SR-002
title: Customers have an email address
statement: A customer record carries one email address.
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    for text in (INT, SR, SR2):
        write_record(repo, text)
    (repo / "src").mkdir()
    (repo / "src" / "billing.py").write_text("def total(lines):\n    return 0\n", "utf-8")
    (repo / "src" / "orphan.py").write_text("X = 1\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/billing.py"))
    return repo


def _explain(root: Path, capsys, *words: str, command: str = "explain") -> tuple[int, dict]:
    code = cli.main([command, "--root", str(root), "--json", *words])
    return code, json.loads(capsys.readouterr().out)


def test_explain_by_id(records: Path, capsys) -> None:
    code, data = _explain(records, capsys, "SR-001")
    assert code == 0
    assert data["how"] == "id" and data["records"] == ["SR-001"]
    text = "\n".join(data["lines"])
    assert 'SR-001 "Invoice totals are rounded to the cent" (proposed' in text
    # the fixture's quote was never checked against a logged prompt, so it is not called
    # "your words" (audit round 2, text.quote_label)
    assert ('quoted, not checked against your logged prompt: "invoice totals should be '
            'rounded to the cent"') in text
    assert "example EX-1: given lines 0.105 and 0.2, when totalled, then the total is 0.31" \
        in text
    assert "code: src/billing.py" in text


def test_explain_by_path(records: Path, capsys) -> None:
    code, data = _explain(records, capsys, "src/billing.py")
    assert code == 0
    assert data["how"] == "path" and data["records"] == ["SR-001"]
    assert data["lines"][0] == "src/billing.py is code for:"
    code, data = _explain(records, capsys, "src/orphan.py")
    assert code == 1
    assert "no requirement owns this file yet" in data["lines"][0]


def test_explain_by_plain_words(records: Path, capsys) -> None:
    code, data = _explain(records, capsys, "how", "are", "invoice", "totals", "rounded?")
    assert code == 0
    assert data["how"] == "words"
    assert data["records"][0] in ("SR-001", "INT-001")
    assert "SR-002" not in data["records"]
    code, data = _explain(records, capsys, "zzz", "qqq")
    assert code == 1 and data["records"] == []


def test_why_is_an_alias_of_explain(records: Path, capsys) -> None:
    code, data = _explain(records, capsys, "SR-001", command="why")
    assert code == 0 and data["records"] == ["SR-001"]
