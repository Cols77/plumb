"""P5: /plumb review, the deep review in the owner's terms (sp5 6.2, SR-064)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from present_helpers import FEAT1, INT1, SR1, SR2, fake_capture, run_prompt, write_all

from plumb import approvals, cli
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-064")

DEC = """---
id: DEC-001
title: Rounding mode
chosen: half-up
alternatives: [banker's rounding]
matters: true
---
"""


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, INT1, FEAT1, DEC)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    return repo


def _review(repo: Path, capsys, *words: str) -> str:
    assert cli.main(["review", "--root", str(repo), *words]) == 0
    return capsys.readouterr().out


def test_review_has_the_five_sections(records: Path, capsys) -> None:
    out = _review(records, capsys)
    for heading in ("1. awaits you:", "2. approvals you did not type", "3. drift:",
                    "4. alignment:", "5. merge state"):
        assert heading in out
    # CAPTURE's triage rates each awaiting record (heuristic backend once merged)
    assert 'INT-001 "add multiply next to add" (riskier' in out
    assert 'question DEC-001 "Rounding mode": assumed half-up' in out
    assert "gap: SR-002 has no code" in out
    assert "it approves nothing" in out


def test_glance_lists_relayed_approvals_with_the_revoke_form(records: Path, hook_input,
                                                             capsys) -> None:
    text = "ok SR-001"
    run_prompt(records, hook_input, text)
    approvals.relay(open_core(records), ["SR-001"], prompt=approvals.prompt_digest(text),
                    quote="ok SR-001")
    out = _review(records, capsys)
    assert 'SR-001 "add returns the sum of two numbers" relayed from your words "ok SR-001"' \
        in out
    assert "plumb revoke <ID>" in out


def test_drift_and_scope_by_plain_words(records: Path, capsys) -> None:
    (records / "src" / "calc.py").write_text("def add(a, b):\n    return b + a\n", "utf-8")
    out = _review(records, capsys, "how", "numbers", "are", "added")
    assert out.startswith("plumb review of SR-001")
    assert "1 stale link(s): SR-001#0 -> src/calc.py" in out
    assert "DEC-001" not in out  # out of scope


def test_triage_groups_from_capture(records: Path, capsys, monkeypatch) -> None:
    item = SimpleNamespace(id="SR-002", title="divide returns the quotient", score=0.4,
                           rating="riskier", excluded=None)
    view = SimpleNamespace(available=True, offer="plumb: approve the 1 record rated "
                           "faithful to your words: \"add\" (SR-001)? say \"ok\"",
                           low_risk=(), individual=(item,))
    fake_capture(monkeypatch, triage=lambda core, ids: view,
                 drift_hints=lambda core, changed: ["plumb: hint: SR-002 may depend on "
                                                    "INT-001"],
                 ownership_proposals=lambda core, paths: {})
    out = _review(records, capsys)
    assert "approve the 1 record rated faithful to your words" in out
    assert 'SR-002 "divide returns the quotient" (riskier 0.40)' in out
    assert "hint: SR-002 may depend on INT-001" in out
