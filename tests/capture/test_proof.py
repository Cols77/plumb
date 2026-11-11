"""SR-127 (DEC-037): a requirement's proof plan and evidence; ``iaso proof``, ``iaso show``,
``iaso capture`` and ``iaso validate`` read them, and recording them confirms nothing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import run

from iaso import approvals
from iaso.api import open_core
from iaso.contracts import Target
from iaso.validate import validate

pytestmark = pytest.mark.sr("SR-253")

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR1 = """---
id: SR-001
title: The panel draws the card
statement: The panel draws the owner's card.
examples:
- id: EX-1
  given: a proposed record
  when: the panel opens
  then: its card is drawn
---
"""


@pytest.fixture
def sr(repo: Path, write_record) -> Path:
    write_record(repo, INT)
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "panel.py").write_text("x = 1\n", encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/panel.py"))
    return repo


def test_old_record_without_proof_stays_valid_and_shows_not_shown(sr: Path, capsys) -> None:
    assert not [f for f in validate(open_core(sr)) if f.code == "proof"]
    assert run(sr, "show", "SR-001") == 0
    out = capsys.readouterr().out
    assert "SR-001 proof: none planned" in out
    assert "SR-001 evidence: not shown working yet" in out


def test_plan_then_evidence_printed_by_show(sr: Path, capsys) -> None:
    """EX-2: the proof and its evidence (where to see it) are printed."""
    assert run(sr, "proof", "SR-001", "--plan", "open a live session and capture the panel",
               "--kind", "live-session") == 0
    (sr / "proof").mkdir()
    (sr / "proof" / "panel.txt").write_text("the card is drawn\n", encoding="utf-8")
    assert run(sr, "proof", "SR-001", "--evidence", "proof/panel.txt", "--summary",
               "the card shows SR-001", "--passed") == 0
    capsys.readouterr()
    assert run(sr, "show", "SR-001") == 0
    out = capsys.readouterr().out
    assert "SR-001 proof (live-session): open a live session and capture the panel" in out
    assert "SR-001 evidence (shown working," in out
    assert "the card shows SR-001" in out
    assert "SR-001 evidence at: proof/panel.txt" in out
    record = open_core(sr).index()["SR-001"]
    assert record.fields["evidence"]["passed"] is True
    assert not [f for f in validate(open_core(sr)) if f.code == "proof"]


def test_recording_proof_neither_confirms_nor_unconfirms(sr: Path) -> None:
    core = open_core(sr)
    before = core.index()["SR-001"].hash
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert run(sr, "proof", "SR-001", "--plan", "run iaso show", "--kind", "command") == 0
    core = open_core(sr)
    assert core.index()["SR-001"].hash == before
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    approvals.approve(core, ["SR-001", "INT-001"])
    assert run(sr, "proof", "SR-001", "--evidence", "https://example.com/run/1",
               "--summary", "printed", "--failed") == 0
    core = open_core(sr)
    assert core.status(["SR-001"])["SR-001"].confirmation == "confirmed"
    assert all(s.state == "current" for s in core.link_states(["SR-001"]))


def test_evidence_needs_summary_outcome_and_an_existing_path(sr: Path, capsys) -> None:
    assert run(sr, "proof", "SR-001", "--evidence", "nowhere.txt", "--summary", "x",
               "--passed") == 2
    assert run(sr, "proof", "SR-001", "--evidence", "https://x.test/a", "--passed") == 2
    assert run(sr, "proof", "SR-001", "--evidence", "https://x.test/a", "--summary", "x") == 2
    assert run(sr, "proof", "SR-001", "--plan", "x", "--kind", "screenshot") == 2
    assert run(sr, "proof", "SR-999", "--plan", "x") == 2
    assert "evidence" not in open_core(sr).index()["SR-001"].fields


def test_a_changed_plan_drops_the_old_evidence(sr: Path, capsys) -> None:
    run(sr, "proof", "SR-001", "--plan", "first", "--kind", "command")
    run(sr, "proof", "SR-001", "--evidence", "https://x.test/1", "--summary", "ok", "--passed")
    run(sr, "proof", "SR-001", "--kind", "hook")  # same plan: evidence kept
    assert "evidence" in open_core(sr).index()["SR-001"].fields
    capsys.readouterr()
    assert run(sr, "proof", "SR-001", "--plan", "second") == 0
    assert "earlier evidence was dropped" in capsys.readouterr().out
    fields = open_core(sr).index()["SR-001"].fields
    assert fields["proof"] == {"plan": "second", "kind": "hook"} and "evidence" not in fields


def test_capture_takes_a_proof_per_requirement_and_names_those_without(sr: Path,
                                                                       capsys) -> None:
    """EX-1: the agent captures a drawing change with a live session capture as its proof."""
    doc = {"intent": "INT-001", "requirements": [
        {"title": "the band shows", "examples": [{"given": "a", "when": "b", "then": "c"}],
         "proof": {"plan": "a live session capture showing the band", "kind": "live-session"}},
        {"title": "no proof here", "examples": [{"given": "a", "when": "b", "then": "c"}]}]}
    path = sr / "capture.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert run(sr, "capture", "--file", str(path)) == 0
    out = capsys.readouterr().out
    index = open_core(sr).index()
    assert index["SR-002"].fields["proof"] == {
        "plan": "a live session capture showing the band", "kind": "live-session"}
    assert "no proof planned for SR-003" in out and "SR-002" not in out.split(
        "no proof planned")[1].splitlines()[0]
    bad = {"intent": "INT-001", "requirements": [
        {"title": "x", "proof": {"plan": "p", "kind": "screenshot"}}]}
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert run(sr, "capture", "--file", str(path)) == 2


def test_capture_update_sets_a_proof_without_asking_the_owner_again(sr: Path, capsys) -> None:
    approvals.approve(open_core(sr), ["SR-001", "INT-001"])
    doc = {"updates": [{"id": "SR-001", "proof": {"plan": "run it", "kind": "command"}}]}
    path = sr / "capture.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert run(sr, "capture", "--file", str(path)) == 0
    out = capsys.readouterr().out
    assert "needs the owner again" not in out
    core = open_core(sr)
    assert core.status(["SR-001"])["SR-001"].confirmation == "confirmed"
    assert core.index()["SR-001"].fields["proof"]["kind"] == "command"


def test_malformed_proof_is_a_warning_never_an_error(sr: Path, write_record) -> None:
    write_record(sr, SR1.replace("SR-001", "SR-002").replace(
        "examples:", "proof: {plan: '', kind: screenshot}\nevidence: {passed: maybe}\nexamples:"))
    findings = [f for f in validate(open_core(sr)) if f.code == "proof"]
    assert findings and {f.severity for f in findings} == {"warning"}
    text = " ".join(f.message for f in findings)
    assert "no plan" in text and "screenshot" in text and "true or false" in text


def _drawing_sr(sr: Path) -> None:
    (sr / "plugin" / "hooks").mkdir(parents=True)
    (sr / "plugin" / "hooks" / "register.tsx").write_text("export {}\n", encoding="utf-8")
    open_core(sr).add_link("SR-001", "implemented_by", Target(path="plugin/hooks/register.tsx"))


def test_ex1_a_drawing_change_without_a_live_session_proof_is_named(sr: Path, capsys) -> None:
    """EX-1: a requirement implemented by the panel's code (what Claude Code draws) whose proof
    is not a live session capture is named when captured and when its plan is recorded; with
    a live session capture it is not. Never a hold."""
    _drawing_sr(sr)
    doc = {"updates": [{"id": "SR-001", "proof": {"plan": "run the tests", "kind": "command"}}]}
    path = sr / "capture.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert run(sr, "capture", "--file", str(path)) == 0
    out = capsys.readouterr().out
    assert "SR-001 changes what Claude Code draws (plugin/hooks/register.tsx)" in out
    assert "--kind live-session" in out
    assert run(sr, "proof", "SR-001", "--plan", "pytest", "--kind", "command") == 0
    assert "changes what Claude Code draws" in capsys.readouterr().out
    assert run(sr, "proof", "SR-001", "--plan", "a live session capture showing the band",
               "--kind", "live-session") == 0
    assert "changes what Claude Code draws" not in capsys.readouterr().out


def test_code_that_draws_nothing_gets_no_such_line(sr: Path, capsys) -> None:
    from iaso.capture.proof import draws

    assert run(sr, "proof", "SR-001", "--plan", "pytest", "--kind", "command") == 0
    assert "changes what Claude Code draws" not in capsys.readouterr().out
    assert draws("plugin/hooks/cards.tsx") and draws("plugin\\hooks\\iaso.ts")
    assert not draws("plugin/hooks/guard.gen.ts") and not draws("src/iaso/mod/session.py")
    assert not draws("plugin/hooks/hooks.json")
