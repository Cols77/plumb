"""SP8 lane JUDGE, J7: the end-of-turn summary (SR-105; SR-104 EX-3; SR-111 EX-5)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion
from plumb.hosts.claude_code.hookio import Deadline, HookContext
from plumb.present import owner_text
from understand.fakes import as_worker, owner_level
from understand.test_judge_job import verdict_answer
from understand.test_settle import (
    SESSION,
    calibration_passing,
    judged,
    make_world,
    settling_on,
)

pytestmark = pytest.mark.sr("SR-105")


@pytest.fixture(autouse=True)
def in_repo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)


def context(repo: Path, budget_ms: float = 1400) -> HookContext:
    return HookContext("stop", {}, repo, SESSION, Deadline(budget_ms))


def parts(repo: Path, **turn: Any):
    from plumb.understand import summary

    return summary.stop_parts(context(repo), open_core(repo),
                              {"turn_start": time.time() - 3600, **turn})


def settle_all(repo: Path, ids: list[str], scores: list[float] | None = None) -> None:
    """Settling on; the worker applies a judgment and writes what it returns."""
    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids, scores or [0.95] * len(ids))
    core = open_core(repo)
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])


def own_card(repo: Path, card: CardState) -> None:
    from plumb.understand import cardstore

    cardstore.save(repo, SESSION, [*cardstore.own_cards(repo, SESSION), card])


def test_sr105_ex1_two_settled_one_line_undo_each(repo: Path, write_record) -> None:
    ids = make_world(repo, write_record, 2)
    settle_all(repo, ids)
    out = parts(repo)
    (line,) = out.settled
    assert line.startswith("Settled from your words: Operation 1 (Undo); Operation 2 (Undo)")
    assert "/plumb undo" in line and owner_level(line) == []
    again = parts(repo)
    assert again.settled == ()                          # said once


def test_a_record_settled_then_undone_is_not_in_the_line(repo: Path, write_record,
                                                          capsys) -> None:
    from plumb.understand import cmd_settle

    ids = make_world(repo, write_record, 2)
    settle_all(repo, ids)
    assert cmd_settle.run("undo", ["Operation", "1", "--root", str(repo)]) == 0
    (line,) = parts(repo).settled
    assert "Operation 2 (Undo)" in line and "Operation 1" not in line


def test_sr105_ex2_beyond_card_offers_keep_drop_reword(repo: Path, write_record) -> None:
    from plumb.understand import cardstore, judge

    ids = make_world(repo, write_record, 1)
    job = judge.build(open_core(repo), SESSION, records=ids)
    applied = judge.apply(open_core(repo), job, verdict_answer(
        (ids[0], "beyond", 0.9), beyond={ids[0]: ["a promise the owner did not make"]}))
    cardstore.save(repo, SESSION, applied.cards)
    (card,) = parts(repo).cards
    assert "goes beyond your words" in card and '"Operation 1"' in card
    assert "a promise the owner did not make" in card
    assert "1. " + owner_text.BEYOND_KEEP in card
    assert owner_text.BEYOND_DROP in card and owner_text.BEYOND_REWORD in card
    assert owner_level(card) == []


def test_order_confirmations_settled_cards(repo: Path, write_record,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import stop
    from plumb.understand import cardstore, read

    ids = make_world(repo, write_record, 2)
    settle_all(repo, ids[:1])
    monkeypatch.setattr(read, "confirmation_lines", lambda core, turn=None: [
        "Operation 2: you said: yes please"], raising=False)
    cardstore.save(repo, SESSION, [CardState(
        id="beyond:x", kind="beyond", topic="Operation 2", issue="more than you said",
        evidence="e", resolutions=("a", "b"))])
    out = stop.understand_parts(context(repo), open_core(repo),
                                {"turn_start": time.time() - 3600})
    assert out[0] == "Operation 2: you said: yes please"
    assert out[1].startswith("Settled from your words")
    assert "goes beyond your words" in out[2]
    assert len(out) == 3


def card(kind: str, **fields: Any) -> CardState:
    base = dict(id=f"{kind}:1", kind=kind, topic="Pages load fast",
                issue="it asks for a thing you did not say",
                evidence="You said: pages should load faster",
                resolutions=("Keep it", "Drop it", "Reword it"),
                questions=(ClarifyQuestion(id=f"{kind}:1#1", text="Pages load fast",
                                           record="SR-001"),))
    base.update(fields)
    return CardState(**base)


@pytest.mark.parametrize("kind", ["clarify", "trial", "backlog", "beyond", "contradicts",
                                  "couldnt_check", "show_first", "stale_link", "settle_offer"])
def test_each_card_kind_names_topic_issue_evidence_resolutions(kind: str) -> None:
    from plumb.understand import cards

    text = cards.render(card(kind))
    assert "Pages load fast" in text                                    # the topic
    assert "it asks for a thing you did not say" in text                # the issue
    assert "Evidence: You said: pages should load faster" in text       # the evidence
    lines = text.splitlines()
    numbered = [line.strip() for line in lines if line.strip()[:2] in ("1.", "2.", "3.")]
    assert numbered == ["1. Keep it", "2. Drop it", "3. Reword it"]     # recommended first
    assert text.splitlines()[0] != lines[1]
    many = cards.render(card(kind, resolutions=("a", "b", "c", "d", "e")))
    assert "4." not in many                                             # two or three, no more


def test_a_card_without_evidence_or_resolutions_renders_what_it_has() -> None:
    from plumb.understand import cards

    text = cards.render(card("couldnt_check", evidence="", resolutions=()))
    assert "Evidence" not in text and "1." not in text


def test_a_batch_card_lists_its_items_in_the_owners_terms() -> None:
    from plumb.understand import cards

    batch = card("trial", questions=(
        ClarifyQuestion(id="t#1", text="Add numbers", record="SR-001"),
        ClarifyQuestion(id="t#2", text="Subtract numbers", record="SR-002")))
    text = cards.render(batch)
    assert "- Add numbers" in text and "- Subtract numbers" in text
    assert "SR-001" not in text


def test_owner_text_passes_both_scanners(repo: Path, write_record) -> None:
    from plumb.understand import cards, cardstore, judge

    ids = make_world(repo, write_record, 3)
    settle_all(repo, ids[:1])
    job = judge.build(open_core(repo), SESSION, records=ids[1:])
    applied = judge.apply(open_core(repo), job, verdict_answer(
        (ids[1], "beyond", 0.9), (ids[2], "contradicts", 0.9),
        beyond={ids[1]: ["SR-002 says more than you did"]},
        contradicts={ids[2]: ["SR-003 EX-1 conflicts with SR-001 EX-1"]}))
    cardstore.save(repo, SESSION, applied.cards)
    out = parts(repo)
    texts = [*out.settled, *out.cards]
    assert texts
    for text in texts:
        assert owner_level(text) == [], text
    for kind in ("clarify", "trial", "backlog", "beyond", "contradicts", "couldnt_check",
                 "show_first", "stale_link", "settle_offer"):
        assert owner_level(cards.render(card(kind))) == [], kind


def test_stop_budget_holds(repo: Path, write_record) -> None:
    """The settled line fits the stop hook's 1400 ms: the minimum of several runs, 0.9 of the
    budget (as tests/host/test_hook_perf.py does)."""
    ids = make_world(repo, write_record, 24)
    settle_all(repo, ids)
    runs = []
    for _ in range(3):
        started = time.perf_counter()
        out = parts(repo)
        runs.append(time.perf_counter() - started)
        (repo / ".plumb" / "session" / SESSION / "told.json").unlink(missing_ok=True)
    assert min(runs) < 1.4 * 0.9
    # a deadline already passed still gives the settled line and nothing else heavy
    from plumb.understand import summary

    expired = HookContext("stop", {}, repo, SESSION, Deadline(0))
    (repo / ".plumb" / "session" / SESSION / "told.json").unlink(missing_ok=True)
    out = summary.stop_parts(expired, open_core(repo), {"turn_start": time.time() - 3600})
    assert out.settled and out.settled[0].startswith("Settled from your words")


def test_couldnt_check_line_after_a_failed_job(repo: Path, write_record,
                                               engine_standins) -> None:
    """SR-104 EX-3: the line says what was not done and that it will be tried again."""
    from plumb.understand import judge, queue, worker

    ids = make_world(repo, write_record, 1)
    job = judge.build(open_core(repo), SESSION, records=ids)
    queue.enqueue(open_core(repo), job)
    engine_standins.dispatcher.failing("run", "the model could not be reached")
    worker.run_once(open_core(repo), SESSION)
    (line,) = parts(repo).cards
    assert "I could not check" in line and "try again" in line
    assert owner_level(line) == []
    assert job.id not in line


def test_a_failed_clarify_job_asks_to_build_without_the_check(repo: Path,
                                                              engine_standins) -> None:
    from plumb.understand import files, summary

    path = files.results_dir(repo, SESSION) / "clarify-0000000000000001.json"
    files.write_json_atomic(files.jobs_dir(repo, SESSION) / "clarify-0000000000000001.json",
                            {"v": 1, "id": "clarify-0000000000000001", "kind": "clarify",
                             "session": SESSION, "schema": "clarify.v1", "needs": None,
                             "inputs": {}, "inputs_digest": ""})
    files.write_json_atomic(path, {"v": 1, "job": "clarify-0000000000000001", "status": "error",
                                   "answer": None, "error": {"step": "run", "message": "down"},
                                   "model": "", "dispatcher": "fake", "started": "t",
                                   "finished": "t", "run_s": 0})
    line = "\n".join(summary.stop_parts(context(repo), open_core(repo), {}).cards)
    assert owner_text.GATE_BUILD_ANYWAY in line and owner_text.GATE_WAIT in line


def test_stale_link_card_rendered_by_the_summary_exactly_once(repo: Path) -> None:
    """SR-111 EX-5 carried over: the adapter feeds the summary, which renders it once."""
    path = repo / ".plumb" / "session" / SESSION / "stale_cards.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "link": "SR-001#0", "record": "SR-001", "path": "src/calc.py", "topic": "Add multiply",
        "issue": "the code changed after you confirmed it",
        "options": ["keep it as is", "reword the requirement", "undo the change"],
        "recommended": 1, "turn": 3, "status": "open"}]), encoding="utf-8")
    out = parts(repo)
    (line,) = out.cards
    assert line.count("Add multiply") == 1
    assert "Something you confirmed may have changed" in line
    assert "1. reword the requirement" in line           # the recommended first
    assert parts(repo).cards == out.cards                # every stop shows it while it is open


def test_the_notice_that_settling_switched_on_is_said_once(repo: Path) -> None:
    calibration_passing(open_core(repo), kinds=("example-restatement",))
    first = parts(repo)
    assert owner_text.SETTLE_ON_REQUIREMENTS in first.settled
    assert owner_text.SETTLE_ON_REQUIREMENTS not in parts(repo).settled


def test_the_offer_to_settle_intents_is_a_card_said_once(repo: Path) -> None:
    calibration_passing(open_core(repo), kinds=("intent-readback",))
    first = parts(repo)
    (card_text,) = first.cards
    assert "/plumb settle on intent" in card_text
    assert parts(repo).cards != ()                       # the card stays until answered
    offers = [e for e in open_core(repo).events() if e.kind == "settle-config"]
    assert len(offers) == 1                              # the owner was told once


def test_an_undone_record_is_carded_next_turn(repo: Path, write_record, capsys) -> None:
    from plumb.understand import cmd_settle

    ids = make_world(repo, write_record, 1)
    settle_all(repo, ids)
    assert cmd_settle.run("undo", ["SR-001", "--root", str(repo)]) == 0
    (card_text,) = parts(repo).cards
    assert "Operation 1" in card_text and "took this back" in card_text
    assert card_text.count("Operation 1") >= 1
    assert owner_level(card_text) == []
