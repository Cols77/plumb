"""CAPTURE C1: plumb new, intent, example and decide (sp2 5.2, SR-035)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.cli import main

pytestmark = pytest.mark.sr("SR-236")

SR_004 = """---
id: SR-004
title: Approvals pin exact content
statement: An approval pins the record hash.
examples:
- id: EX-1
  given: an approved requirement
  when: its statement is edited
  then: the requirement is an unconfirmed edit
- id: EX-2
  given: an approval
  when: the record is unchanged
  then: it stays confirmed
---
"""


def run(repo: Path, *argv: str) -> int:
    return main([*argv, "--root", str(repo)])


def test_new_uses_next_id_and_is_proposed(repo: Path, write_record, capsys) -> None:
    write_record(repo, SR_004)
    assert run(repo, "new", "requirement", "--title", "multiply returns the product",
               "--statement", "multiply(a, b) returns a * b") == 0
    out = capsys.readouterr().out
    assert "SR-005" in out and ".plumb/requirements/SR-005.md" in out
    core = open_core(repo)
    record = core.index()["SR-005"]
    assert record.fields["statement"] == "multiply(a, b) returns a * b"
    assert core.status(["SR-005"])["SR-005"].confirmation == "proposed"
    assert run(repo, "new", "intent", "--title", "x") == 2  # an INT needs the owner's words


def test_intent_records_quote_readback_and_lists(repo: Path, capsys) -> None:
    assert run(repo, "intent", "--quote", "add multiply next to add", "--readback",
               "Add multiply beside add", "--will", "multiply(a, b) returns a * b",
               "--wont", "no floats yet", "--assume", "integers only, like add") == 0
    record = open_core(repo).index()["INT-001"]
    assert record.fields["quote"] == "add multiply next to add"
    assert record.fields["will"] == ["multiply(a, b) returns a * b"]
    assert record.fields["wont"] == ["no floats yet"]
    assert record.fields["assumptions"] == ["integers only, like add"]
    assert "INT-001 proposed" in capsys.readouterr().out


def test_example_appends_ex_n(repo: Path, write_record, capsys) -> None:
    write_record(repo, SR_004)
    before = open_core(repo).index()["SR-004"].hash
    assert run(repo, "example", "SR-004", "--given", "G", "--when", "W", "--then", "T",
               "--quote", "the owner said T") == 0
    record = open_core(repo).index()["SR-004"]
    assert [e.id for e in record.examples] == ["EX-1", "EX-2", "EX-3"]
    assert record.fields["examples"][2]["quote"] == "the owner said T"
    assert record.hash != before
    assert "SR-004 EX-3" in capsys.readouterr().out
    assert open_core(repo).status(["SR-004"])["SR-004"].confirmation == "proposed"
    assert run(repo, "example", "SR-404", "--given", "G", "--when", "W", "--then", "T") == 2


def test_decide_writes_alternatives_and_matters(repo: Path, write_record, capsys) -> None:
    write_record(repo, SR_004)
    assert run(repo, "decide", "--question", "Floats too?", "--chosen", "integers only",
               "--alt", "floats too", "--matters", "--recommend", "integers only",
               "--decides", "SR-004") == 0
    core = open_core(repo)
    dec = core.index()["DEC-001"]
    assert dec.fields["chosen"] == "integers only"
    assert dec.fields["alternatives"] == ["floats too"]
    assert dec.fields["matters"] is True
    assert dec.fields["recommended"] == "integers only"
    assert [(link.kind, link.target.record) for link in dec.links] == [("decides", "SR-004")]
    assert all(link.pin is not None for link in dec.links)
    assert core.status(["DEC-001"])["DEC-001"].confirmation == "proposed"
    assert "I assumed integers only; floats too also fits" in capsys.readouterr().out
    assert run(repo, "decide", "--question", "Q", "--chosen", "A", "--alt", "B",
               "--recommend", "C") == 2


def test_supersede_never_edits_confirmed_dec(repo: Path, write_record) -> None:
    from plumb.approvals import approve

    write_record(repo, SR_004)
    assert run(repo, "decide", "--question", "Floats too?", "--chosen", "integers only",
               "--alt", "floats too", "--decides", "SR-004") == 0
    core = open_core(repo)
    approve(core, ["DEC-001"])  # the owner (the test stands in for the owner's terminal)
    old_bytes = (repo / ".plumb" / "decisions" / "DEC-001.md").read_bytes()
    assert run(repo, "decide", "--supersede", "DEC-001", "--chosen", "floats too") == 0
    core = open_core(repo)
    new = core.index()["DEC-002"]
    assert ("supersedes", "DEC-001") in [(lk.kind, lk.target.record) for lk in new.links]
    assert ("decides", "SR-004") in [(lk.kind, lk.target.record) for lk in new.links]
    assert new.fields["alternatives"] == ["integers only"]
    assert (repo / ".plumb" / "decisions" / "DEC-001.md").read_bytes() == old_bytes
    assert core.status(["DEC-001"])["DEC-001"].confirmation == "confirmed"
    assert core.status(["DEC-001"])["DEC-001"].superseded_by == "DEC-002"
