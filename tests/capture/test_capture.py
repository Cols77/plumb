"""CAPTURE C2: iaso capture writes a whole read-back in one call (sp2 5.1, SR-034)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import event_kinds, log_prompt, run, tree_bytes

from iaso.api import open_core

pytestmark = pytest.mark.sr("SR-235")

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
    from iaso.approvals import approve

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
    assert tree_bytes(calc) == before
    assert event_kinds(calc) == []


def test_prints_what_it_wrote_and_no_intent_card(calc: Path, capsys) -> None:
    """INT-037: the owner reads the request's read-back card, not a second card of ids."""
    assert capture(calc, DOC) == 0
    out = capsys.readouterr().out
    assert "INT-001 proposed" in out and "SR-001 proposed" in out
    assert "▸ Intent" not in out and "say \"ok\"" not in out


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


class _Judge:
    name = "fake"

    def __init__(self, verdict: str) -> None:
        self.verdict = verdict

    def contradiction(self, prompt, record):
        from iaso.contracts import Judgment

        return Judgment(action="contradiction", subject=record.id, verdict=self.verdict,
                        confidence=0.9, tier="act", backend="fake", fingerprint="f")


def _relay_doc(statement: str, **extra) -> dict:
    return {"intent": {"quote": "x", "readback": "relay"},
            "requirements": [{"title": statement, "statement": statement, **extra}]}


@pytest.mark.sr("SR-237")
def test_capture_names_the_requirement_a_new_one_contradicts(calc: Path) -> None:
    """SR-165 EX-2: 'never relays the choice' next to 'relays the choice'."""
    from iaso.capture.capture import capture as run

    core = open_core(calc)
    first = run(core, _relay_doc("The agent relays the choice the owner made"),
                backend=_Judge("benign"))
    second = run(open_core(calc), _relay_doc("The agent never relays the choice the owner made"),
                 backend=_Judge("contradicts"))
    old, new = first.written[1], second.written[1]
    assert any(f"{new} contradicts {old}" in line and f"supersedes: [{old}]" in line
               for line in second.lines)


@pytest.mark.sr("SR-237")
def test_capture_supersedes_adds_the_link_and_names_nothing_for_it(calc: Path) -> None:
    from iaso.capture.capture import CaptureError, capture as run

    first = run(open_core(calc), _relay_doc("The agent relays the choice the owner made"))
    old = first.written[1]
    second = run(open_core(calc), _relay_doc("The agent never relays the choice",
                                             supersedes=[old]), backend=_Judge("contradicts"))
    new = second.written[1]
    links = open_core(calc).index()[new].links
    assert [(link.kind, link.target.record) for link in links
            if link.kind == "supersedes"] == [("supersedes", old)]
    assert not any("contradicts" in line for line in second.lines)
    with pytest.raises(CaptureError):
        run(open_core(calc), _relay_doc("another", supersedes=["INT-999"]))


def _cover_doc(statement: str) -> dict:
    return {"intent": {"quote": "q", "readback": "r"},
            "requirements": [{"title": statement, "statement": statement}]}


def _live(core, kind: str) -> list[str]:
    from iaso.query import superseded_ids

    gone = superseded_ids(core.index())
    return [r.id for r in core.index().values() if r.kind == kind and r.id not in gone]


@pytest.mark.sr("SR-383")
def test_restated_requirement_supersedes_and_adds_no_near_duplicate(calc: Path) -> None:
    """SR-383 EX-1."""
    from iaso.capture.capture import capture as run

    plan = "The agent shows the owner the plan"
    old = run(open_core(calc), _cover_doc(f"{plan} each turn")).written[1]
    new = run(open_core(calc), _cover_doc(f"{plan} every turn")).written[1]
    core = open_core(calc)
    assert _live(core, "requirement") == [new]
    assert [(k.kind, k.target.record) for k in core.index()[new].links
            if k.kind == "supersedes"] == [("supersedes", old)]


@pytest.mark.sr("SR-383")
def test_restated_decision_is_edited_not_duplicated(calc: Path) -> None:
    """SR-383 EX-1 (decision)."""
    from iaso.capture.capture import capture as run

    def doc(chosen: str) -> dict:
        return {"intent": {"quote": "q", "readback": "r"},
                "decisions": [{"question": "Which store keeps the owner answers?",
                               "chosen": chosen, "alternatives": ["none"]}]}

    first = run(open_core(calc), doc("the log"))
    dec = first.written[1]
    run(open_core(calc), doc("the question tool"))
    core = open_core(calc)
    assert _live(core, "decision") == [dec]
    assert core.index()[dec].fields["chosen"] == "the question tool"


@pytest.mark.sr("SR-383")
def test_uncovered_topic_still_creates_a_record(calc: Path) -> None:
    """SR-383 EX-2."""
    from iaso.capture.capture import capture as run

    run(open_core(calc), _cover_doc("The agent shows the owner the plan each turn"))
    run(open_core(calc), _cover_doc("Backups of the log run nightly"))
    assert len(_live(open_core(calc), "requirement")) == 2
