"""SR-251, SR-267: a judge approval is marked "judge-approved (judge, model, score)" wherever
the record is listed and counted at the turn end; an entry below the bar is inert and validate
warns; what the owner reads (status, brief, the turn line, the session start) names no approve
or confirm hint and no record id. The judge model is a stub (``test_auto_model.judged``)."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from understand.fakes import as_worker
from understand.test_auto_model import judged
from understand.test_judge_cascade import calibrate_to, configure
from understand.test_judge_job import SESSION
from understand.test_round_approval import owner_answers, world  # noqa: F401

from plumb import cli
from plumb.api import open_core
from plumb.approvals import approval_items
from plumb.understand import judge

LABEL = "judge-approved (auto-model, haiku, 0.8)"
COUNTED = "1 approved on your behalf by the judge"
HINT = re.compile(r"/plumb approve|plumb approve|plumb revoke|plumb triage|your confirmation"
                  r"|confirm (it|them)|say ok|ok to\b", re.I)
ID = re.compile(r"\b(?:INT|SR|DEC|FEAT)-\d{3}\b")


def _cli(capsys, *argv: str) -> str:
    assert cli.main(list(argv)) == 0
    return capsys.readouterr().out


def _turn_end(root: Path) -> tuple[tuple[str, ...], str]:
    """The stop hook's confirmations (the agent's), then the owner's one plumb line."""
    from plumb.understand.summary import Told, _confirmations, owner_line

    told = Told(root, SESSION, "2000-01-01T00:00:00Z")
    lines = _confirmations(open_core(root), None, told)
    return lines, owner_line(open_core(root), SESSION)


def _session_start(root: Path, hook_input) -> str:
    from plumb.hosts.claude_code import session_start

    out = io.StringIO()
    assert session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                              stdout=out, root=root, verify=None) == 0
    return out.getvalue()


@pytest.mark.sr("SR-251")
def test_ex1_the_turn_end_counts_a_judge_approval_and_every_listing_labels_it(
        world: Path, capsys) -> None:  # noqa: F811
    """SR-251 EX-1: the judge model approved SR-001 during the turn: the plumb line counts one
    judge approval and SR-001 shows as judge-approved (auto-model, haiku, 0.8) wherever it is
    listed (show, explain, status, the status card)."""
    judged(world, ("SR-001", "supported", 0.8))
    lines, line = _turn_end(world)
    # SR-265 EX-7: the count is the agent's and the status line's; the owner gets no line
    assert lines == (COUNTED,) and line == ""
    root = ["--root", str(world)]
    assert _cli(capsys, "show", *root, "SR-001").startswith(f"SR-001 (requirement, {LABEL}) ")
    assert LABEL in _cli(capsys, "explain", *root, "SR-001")
    assert f"Pages load in two seconds: {LABEL}" in _cli(capsys, "status", *root)
    assert f"Pages load in two seconds: {LABEL}" in _cli(capsys, "status", "--card", *root)


@pytest.mark.sr("SR-251")
def test_ex1_the_brief_labels_a_judge_approved_intent(world: Path) -> None:  # noqa: F811
    """SR-251 EX-1: the brief, which lists intents, marks one the judge approved."""
    from plumb.query import brief_lines

    judged(world, ("INT-001", "supported", 0.8))
    (item,) = [x for x in brief_lines(open_core(world)) if x.startswith("  INT-001")]
    assert LABEL in item


@pytest.mark.sr("SR-251")
def test_ex2_an_auto_jev_entry_under_the_floor_is_inert_and_validate_warns(
        world: Path) -> None:  # noqa: F811
    """SR-251 EX-2: a worker wrote a by: auto-jev approval at 0.6, under the cascade's 0.9
    floor: it is refused, SR-001 counts as proposed and plumb validate reports the inert entry
    as a warning, not an error."""
    from plumb.validate import validate

    core = configure(world)
    calibrate_to(core, 0.43)
    digest = owner_answers(world, ["SR-001"])
    core = open_core(world)
    calibration = next(e for e in core.events() if e.kind == "calibration")
    with as_worker(world, SESSION):
        core.log_append("events", "approval", {
            "records": approval_items(core, ["SR-001"]), "by": "auto-jev",
            "prompt_digest": digest, "answers": [digest], "session": SESSION, "job": "j",
            "auto": {"score": 0.6, "confidence_label": "high", "judge": "jev",
                     "model_version": "jev-1", "calibration": calibration.digest,
                     "claim_kind": "example-restatement", "threshold": 0.43}})
    assert open_core(world).status(["SR-001"])["SR-001"].confirmation == "proposed"
    found = [f for f in validate(open_core(world)) if f.subject == "SR-001"
             and f.code in ("inert-approval", "approval")]
    assert [(f.severity, f.code) for f in found] == [("warning", "inert-approval")]


@pytest.mark.sr("SR-267")
def test_what_the_owner_reads_names_no_approve_hint_and_no_id(
        world: Path, capsys, hook_input) -> None:  # noqa: F811
    """Status, the status card, the brief, the turn line and the session start count what
    awaits the owner (the judge's open question with the request it came from, the records
    waiting on a judge) and name no approve or confirm hint and no record id. The brief's own
    listing of intents (indented) is the agent's index and keeps its ids."""
    judged(world, ("SR-001", "supported", 0.8))
    index = open_core(world).index()
    question = 'Every page, or only the public ones?\n\nYou said: "I want pages to load faster"'
    path = judge.questions_path(world, SESSION)
    path.write_text(json.dumps([{
        "key": judge.question_key(question), "job": "judge-1", "question": question,
        "records": [{"id": "INT-001", "hash": index["INT-001"].hash}], "header": "Pages",
        "options": [{"label": "Public (Recommended)", "description": "Only those."},
                    {"label": "Every page", "description": "All of them."}]}]), "utf-8")
    root = ["--root", str(world)]
    status = _cli(capsys, "status", *root)
    assert ('awaits you: 1 question about what you asked (You said: "I want pages to load '
            'faster")') in status
    assert "waiting on a judge: 1 record" in status
    card = _cli(capsys, "status", "--card", *root)
    brief = [x for x in _cli(capsys, "brief", *root).splitlines() if not x.startswith("  ")]
    _, line = _turn_end(world)
    start = _session_start(world, hook_input)
    for text in (status, card, "\n".join(brief), line, start):
        assert not HINT.search(text), text
        assert not ID.search(text.replace(LABEL, "")), text


@pytest.mark.sr("SR-267")
def test_triage_review_and_merge_check_name_no_approve_hint_and_no_id(
        world: Path, capsys) -> None:  # noqa: F811
    """plumb triage, the review's awaits-you, glance and merge-state sections and the quick
    merge check list what waits on a judge by title and count, with no approve or confirm
    hint and no record id."""
    from plumb.boundary.premerge import PremergeReport, render
    from plumb.capture.triage import view_lines
    from plumb.contracts import TriageItem, TriageView

    judged(world, ("SR-001", "supported", 0.8))
    root = ["--root", str(world)]
    item = TriageItem(id="SR-002", hash="sha256:" + "0" * 64, title="Pages are cached",
                      rating="faithful", outcome="faithful")
    triage = view_lines(TriageView(backend="stub", available=True, low_risk=(item,),
                                   individual=(item,)))
    assert "  Pages are cached" in triage
    review = _cli(capsys, "review", *root)
    sections = review.split("3. drift:")[0] + review[review.index("5. merge state"):]
    merge = render(PremergeReport(merging="feat", into="main", exit=4, unconfirmed=(
        {"id": "SR-002", "title": "Pages are cached", "state": "proposed"},)))
    assert '  "Pages are cached" waits on a judge' in merge
    listed = _cli(capsys, "triage", *root).splitlines()[1:]    # under its own header
    for text in ("\n".join(triage[1:]), "\n".join(listed), sections, "\n".join(merge)):
        assert not HINT.search(text), text
        assert not ID.search(text.replace(LABEL, "")), text


@pytest.mark.sr("SR-251")
def test_ex1_the_band_counts_every_record_status_lists_judge_approved(
        world: Path, capsys) -> None:  # noqa: F811
    """SR-251 EX-1: the band's status counts the judge approvals ``plumb status`` lists, of any
    kind (round 3: the band said 2 where status listed 6, its decisions left out)."""
    from plumb.hosts.claude_code.snapshot import build_snapshot

    judged(world, ("SR-001", "supported", 0.8), ("INT-001", "supported", 0.8))
    snap = build_snapshot(open_core(world))
    listed = _cli(capsys, "status", "--root", str(world)).count(LABEL)
    assert snap.judge_approved == listed == 2
    assert snap.confirmed_by.get("auto-model") == 1   # the SR count beside it is unchanged


@pytest.mark.sr("SR-251")
def test_ex1_a_turn_without_an_edit_brings_the_band_count_up_to_date(
        world: Path) -> None:  # noqa: F811
    """SR-251 EX-1: the judge approves between turns; a turn that edits nothing still updates
    the band's count (round 4: the band showed none while status listed 2)."""
    from plumb.hosts.claude_code.snapshot import (build_snapshot, refresh_judge_count,
                                                  write_snapshot)

    write_snapshot(world, build_snapshot(open_core(world)))
    judged(world, ("SR-001", "supported", 0.8), ("INT-001", "supported", 0.8))
    refresh_judge_count(open_core(world))
    data = json.loads((world / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["judge_approved"] == 2
