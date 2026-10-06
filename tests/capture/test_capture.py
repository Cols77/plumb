"""CAPTURE C2: plumb capture writes a whole read-back in one call (sp2 5.1, SR-034)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, run, tree_bytes

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-034")

PROMPT = "please add multiply next to add; 2 times 3 is 6"
DOC = {
    "intent": {"quote": "add multiply next to add", "readback": "Add multiply beside add",
               "will": ["multiply(a, b) returns a * b"], "wont": ["no floats yet"],
               "assumptions": ["integers only, like add"]},
    "requirements": [{"title": "multiply returns the product",
                      "statement": "multiply(a, b) returns a * b",
                      "examples": [{"given": "a = 2 and b = 3", "when": "multiply runs",
                                    "then": "it returns 6", "quote": "2 times 3 is 6"},
                                   {"given": "a = 0", "when": "multiply runs",
                                    "then": "it returns 0"}],
                      "implemented_by": ["src/calc.py"]}],
    "decisions": [{"question": "Floats too?", "chosen": "integers only",
                   "alternatives": ["floats too"], "matters": True,
                   "recommended": "integers only", "decides": ["#1"]}],
}
SR_009 = """---
id: SR-009
title: add returns the sum
statement: add(a, b) returns a + b
examples:
- id: EX-1
  given: a = 1 and b = 2
  when: add runs
  then: it returns 3
---
"""


@pytest.fixture
def calc(repo: Path) -> Path:
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                          encoding="utf-8")
    return repo


def capture(repo: Path, doc: dict, *extra: str, tmp: Path | None = None) -> int:
    path = (tmp or repo) / "capture.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return run(repo, "capture", "--file", str(path), *extra)


def test_capture_writes_int_sr_dec_linked_and_proposed(calc: Path, capsys) -> None:
    digest = log_prompt(calc, PROMPT)
    assert capture(calc, DOC, "--prompt", digest[:20]) == 0
    core = open_core(calc)
    index = core.index()
    assert {"INT-001", "SR-001", "DEC-001"} <= set(index)
    statuses = core.status()
    assert {statuses[i].confirmation for i in ("INT-001", "SR-001", "DEC-001")} == {"proposed"}
    sr = index["SR-001"]
    assert [e.id for e in sr.examples] == ["EX-1", "EX-2"]
    assert sr.fields["examples"][0]["quote"] == "2 times 3 is 6"
    kinds = {(lk.kind, lk.target.record or lk.target.path) for lk in sr.links}
    assert kinds == {("derives_from", "INT-001"), ("implemented_by", "src/calc.py")}
    dec = index["DEC-001"]
    assert {(lk.kind, lk.target.record) for lk in dec.links} == {
        ("derives_from", "INT-001"), ("decides", "SR-001")}
    assert all(s.state == "current" for s in core.link_states())
    assert index["INT-001"].fields["prompt"] == digest.removeprefix("sha256:")[:16]
    out = capsys.readouterr().out
    assert "INT-001 proposed" in out and "SR-001 proposed" in out and "DEC-001 proposed" in out


def test_quote_must_be_verbatim_in_prompt(calc: Path, capsys) -> None:
    digest = log_prompt(calc, "please add a multiplication next to add")
    before = tree_bytes(calc)
    assert capture(calc, DOC, "--prompt", digest) == 2
    assert "not a verbatim part" in capsys.readouterr().err
    assert tree_bytes(calc) == before
    assert event_kinds(calc) == []


def test_update_of_confirmed_record_says_unconfirmed(repo: Path, write_record,
                                                     capsys) -> None:
    from plumb.approvals import approve

    write_record(repo, SR_009)
    approve(open_core(repo), ["SR-009"])
    doc = {"updates": [{"id": "SR-009", "add_examples": [
        {"given": "a = -1 and b = 1", "when": "add runs", "then": "it returns 0"}]}]}
    assert capture(repo, doc) == 0
    core = open_core(repo)
    assert core.status(["SR-009"])["SR-009"].confirmation == "unconfirmed-edit"
    assert [e.id for e in core.index()["SR-009"].examples] == ["EX-1", "EX-2"]
    assert "SR-009 was confirmed; this edit needs the owner again" in capsys.readouterr().out


def test_dry_run_writes_nothing(calc: Path, capsys) -> None:
    before = tree_bytes(calc)
    assert capture(calc, DOC, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "dry run: nothing written" in out
    assert "Add multiply beside add" in out  # the card is printed
    assert tree_bytes(calc) == before
    assert event_kinds(calc) == []


def test_prints_intent_card(calc: Path, capsys) -> None:
    assert capture(calc, DOC) == 0
    out = capsys.readouterr().out
    assert '▸ Intent  INT-001 "Add multiply beside add"' in out
    assert 'proposed — say "ok" to confirm' in out
    assert "Will: multiply(a, b) returns a * b" in out
    assert "Won't: no floats yet" in out and "Assumed: integers only, like add" in out
    assert "SR-001/EX-1 given a = 2 and b = 3" in out


def test_bad_document_writes_nothing(calc: Path) -> None:
    before = tree_bytes(calc)
    bad = {**DOC, "requirements": [{**DOC["requirements"][0],
                                    "implemented_by": ["src/missing.py"]}]}
    assert capture(calc, bad) == 2
    assert capture(calc, {"requirements": DOC["requirements"]}) == 2  # no intent
    assert tree_bytes(calc) == before


def test_escalated_intent_lists_its_members(calc: Path) -> None:
    doc = {**DOC, "intent": {**DOC["intent"], "mode": "escalated"}}
    assert capture(calc, doc) == 0
    core = open_core(calc)
    assert core.index()["INT-001"].fields["members"] == ["SR-001", "DEC-001"]
    assert all(s.state == "current" for s in core.link_states())
