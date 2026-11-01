"""One judge path (INT-037: SR-134, SR-135) and the trial card as one record's read-back
(INT-036: SR-132, SR-133)."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "capture"))
from capture_helpers import log_prompt as hook_prompt  # noqa: E402
from capture_helpers import run  # noqa: E402
from jev_fixtures import calibrated  # noqa: E402

from plumb.api import open_core  # noqa: E402
from plumb.present import owner_text  # noqa: E402
from plumb.understand import cardstore, files, hooks, judge, trial  # noqa: E402
from understand.fakes import as_worker  # noqa: E402
from understand.test_judge_job import (  # noqa: E402
    SESSION,
    decision_text,
    intent_text,
    log_prompt,
    make_world,
    requirement_text,
    verdict_answer,
)

CTX = SimpleNamespace(session_id=SESSION)


def judged(repo: Path, ids: list[str], scores: list[float]) -> Any:
    core = open_core(repo)
    job = judge.build(core, SESSION, records=ids)
    assert job is not None
    answer = verdict_answer(*((i, "supported", s) for i, s in zip(ids, scores, strict=True)))
    return judge.apply(core, job, answer)


def write_applied(repo: Path, applied: Any) -> None:
    core = open_core(repo)
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])


def typed(repo: Path, text: str) -> list[str]:
    digest = hook_prompt(repo, text, session=SESSION)
    return hooks.on_prompt(CTX, open_core(repo), {"digest": digest, "text": text})


# ---- SR-134 ------------------------------------------------------------------------------


@pytest.mark.sr("SR-248")
def test_ex1_a_supported_verdict_alone_confirms_nothing(repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 1)
    applied = judged(repo, ids, [0.99])
    assert [e for e in applied.entries if e["kind"] == "approval"] == []
    assert applied.cards == ()                           # SR-252 EX-6: no trial card either
    assert "settle" not in json.dumps([dataclasses.asdict(c) for c in applied.cards]).lower()
    write_applied(repo, applied)
    assert open_core(repo).status(ids)["SR-001"].confirmation == "proposed"


PROMPT = "add multiply next to add; multiply returns the product of two numbers"
INTENT = {"quote": "add multiply next to add", "readback": "add multiply next to add",
          "will": ["multiply next to add"]}
REQUIREMENT = {"title": "multiply returns the product",
               "statement": "multiply returns the product of two numbers",
               "examples": [{"given": "two numbers", "when": "multiply runs",
                             "then": "it returns the product",
                             "quote": "multiply returns the product of two numbers"}]}


@pytest.fixture
def judge_confirmed(repo: Path, write_record, monkeypatch) -> list[str]:
    """Auto-approve on and calibrated: the owner's words restated are confirmed by the judge."""
    stub = calibrated(repo, write_record, monkeypatch, requirements=True)
    assert run(repo, "config", "auto-approve", "on") == 0
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    before = set(open_core(repo).index())
    path = repo / "doc.json"
    path.write_text(json.dumps({"intent": INTENT, "requirements": [REQUIREMENT]}),
                    encoding="utf-8")
    assert run(repo, "capture", "--file", str(path), "--prompt",
               log_prompt(repo, PROMPT)) == 0
    ids = sorted(set(open_core(repo).index()) - before)
    run_judge_job(repo, ids)          # the fast track runs in the judge job (SR-242)
    yield ids
    stub.close()


def run_judge_job(repo: Path, ids: list[str]) -> None:
    """The judge job over ``ids`` as the worker runs it: JEV first, the fast track, the
    entries written with the worker's token."""
    from plumb.understand import verdict
    from understand.fakes import FakeDispatcher

    core = open_core(repo)
    job = judge.build(core, SESSION, records=ids)
    done = verdict.cascade(core, job, system="judge", schema={}, dispatcher=FakeDispatcher())
    write_applied(repo, judge.apply(core, job, done.answer))


@pytest.mark.sr("SR-248")
def test_ex3_auto_approve_on_and_calibrated_confirms_with_the_judges_verdict(
        repo: Path, judge_confirmed: list[str]) -> None:
    core = open_core(repo)
    assert all(core.status([i])[i].confirmation == "confirmed" for i in judge_confirmed)
    approvals = [e.payload for e in core.log_read("events", ["approval"])
                 if e.payload.get("by") == "auto-jev"]
    assert len(approvals) == 2
    assert approvals[0]["auto"]["score"] >= 0.9 and approvals[0]["auto"]["model_version"]


@pytest.mark.sr("SR-248")
def test_ex2_a_typed_settle_says_the_switch_is_gone_and_changes_nothing(
        repo: Path, write_record) -> None:
    make_world(repo, write_record, 1)
    assert typed(repo, "/plumb settle on intent") == [owner_text.TYPED_SETTLE_GONE]
    assert not list(files.jobs_dir(repo, SESSION).glob("*.json"))     # no request was checked


def test_a_record_the_judge_confirmed_gets_no_trial_card(
        repo: Path, judge_confirmed: list[str]) -> None:
    assert judged(repo, judge_confirmed, [0.99, 0.99]).cards == ()


# ---- SR-135 ------------------------------------------------------------------------------


@pytest.mark.sr("SR-210")
@pytest.mark.parametrize("text", ["/plumb undo {id}", "/plumb:plumb undo {id}"])
def test_ex3_a_typed_undo_is_done_by_the_hook(
        repo: Path, judge_confirmed: list[str], text: str) -> None:
    _, sr = judge_confirmed
    lines = typed(repo, text.format(id=sr))
    assert any("proposed again" in line for line in lines)
    core = open_core(repo)
    assert core.status([sr])[sr].confirmation == "proposed"
    (entry,) = [e for e in core.events()
                 if e.kind == "revocation" and e.payload.get("by") == "undone"]
    assert entry.payload["by"] == "undone" and entry.payload["via"] == "typed"
    from plumb import words

    assert entry.payload["prompt_digest"] and entry.payload["quote_digest"]
    assert words.joined(core, entry)["quote"].startswith("/plumb")   # DEC-116: the words are local
    assert run(repo, "undo", sr) == 2                    # no such command any more


@pytest.mark.sr("SR-210")
def test_ex3_a_typed_undo_of_a_record_nobody_judged_changes_nothing(
        repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 1)
    lines = typed(repo, f"/plumb undo {ids[0]}")
    assert lines and not [e for e in open_core(repo).events() if e.kind == "revocation"]


# ---- SR-133 ------------------------------------------------------------------------------


@pytest.mark.sr("SR-252")
def test_ex1_a_card_is_one_record_with_its_words_and_date(repo: Path, write_record) -> None:
    said = "keep the plain checkout, the shop is small"
    digest = log_prompt(repo, said, at="2026-10-04T10:00:00Z")
    write_record(repo, intent_text(1, said, "A plain checkout", prompt=digest))
    write_record(repo, decision_text(1, "Which checkout?", "plain checkout", intent=1,
                                     alternatives=("a wizard",)))
    assert judged(repo, ["DEC-001"], [0.9]).cards == ()   # SR-252 EX-6: the judge draws none
    core = open_core(repo)                                 # a trial card opened before
    (item,) = judge.entries_for(core, ["DEC-001"])
    card = trial.card(core, trial.Candidate(core.index()["DEC-001"], 0.9, item["premise"]))
    assert card.kind == "trial" and len(card.questions) == 1
    assert card.id.startswith("trial:DEC-001@") and card.topic == "Which checkout?"
    assert said in card.evidence and "4 Oct" in card.evidence
    assert card.issue == "You chose plain checkout over a wizard"
    choices = card.questions[0].choices
    assert [(c.label, c.answer) for c in choices] == [
        ("Yes", "accepted"), ("No", "rejected"), ("Fix it", "change")]
    assert all(c.consequence for c in choices)


@pytest.mark.sr("SR-252")
def test_ex2_words_not_found_say_so_and_show_the_proposal_alone(
        repo: Path, write_record) -> None:
    log_prompt(repo, "something else entirely")
    write_record(repo, requirement_text(1, "Totals", "Totals are shown on the invoice"))
    record = open_core(repo).index()["SR-001"]
    card = trial.card(open_core(repo), trial.Candidate(record, 0.9, {}))
    assert card.evidence == "Your words for this were not found."
    assert card.issue == "Totals are shown on the invoice"


# ---- SR-132 ------------------------------------------------------------------------------


@pytest.mark.sr("SR-216")
def test_ex3_a_card_of_a_branch_that_is_gone_is_not_in_the_backlog(repo: Path) -> None:
    from plumb.contracts import CardState

    cards = [CardState(id="clarify:a", branch="main"), CardState(id="clarify:b", branch="gone"),
             CardState(id="clarify:c")]
    cardstore.save(repo, SESSION, cards)
    assert [c.id for c in cardstore.load(repo, SESSION)] == ["clarify:a", "clarify:c"]


@pytest.mark.sr("SR-216")
def test_ex4_a_withdrawn_card_confirms_nothing_and_its_record_stays_proposed(
        repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 1)
    write_applied(repo, judged(repo, ids, [0.9]))
    drawn = [trial.card(open_core(repo), trial.Candidate(open_core(repo).index()["SR-001"], 0.9,
                                                         {}))]    # a trial card opened before
    cardstore.save(repo, SESSION, drawn)
    cardstore.withdraw(repo, SESSION, [drawn[0].id])
    assert cardstore.load(repo, SESSION) == []
    assert [c.status for c in cardstore.own_cards(repo, SESSION)] == ["withdrawn"]
    assert open_core(repo).status(ids)["SR-001"].confirmation == "proposed"
