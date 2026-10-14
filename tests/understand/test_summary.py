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
from understand.fakes import owner_level
from understand.test_judge_job import verdict_answer
from understand.test_judge_job import SESSION, make_world

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


def own_card(repo: Path, card: CardState) -> None:
    from plumb.understand import cardstore

    cardstore.save(repo, SESSION, [*cardstore.own_cards(repo, SESSION), card])


def test_order_confirmations_then_cards(repo: Path, write_record,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import stop
    from plumb.understand import cardstore, read

    make_world(repo, write_record, 2)
    monkeypatch.setattr(read, "confirmation_lines", lambda core, turn=None: [
        "Operation 2: you said: yes please"], raising=False)
    cardstore.save(repo, SESSION, [CardState(
        id="beyond:x", kind="beyond", topic="Operation 2", issue="more than you said",
        evidence="e", resolutions=("a", "b"))])
    out = stop.understand_parts(context(repo), open_core(repo),
                                {"turn_start": time.time() - 3600})
    assert out[0] == "Operation 2: you said: yes please"
    assert out[1].splitlines()[:2] == ["Operation 2", "more than you said"]
    assert len(out) == 2


def card(kind: str, **fields: Any) -> CardState:
    base = dict(id=f"{kind}:1", kind=kind, topic="Pages load fast",
                issue="it asks for a thing you did not say",
                evidence="You said: pages should load faster",
                resolutions=("Keep it", "Drop it", "Reword it"),
                questions=(ClarifyQuestion(id=f"{kind}:1#1", text="Pages load fast",
                                           record="SR-001"),))
    base.update(fields)
    return CardState(**base)


def drawn(repo: Path, built: CardState) -> str:
    from plumb.understand import fullcard

    return fullcard.render(fullcard.content(open_core(repo), built))


@pytest.mark.parametrize("kind", ["clarify", "trial", "beyond", "contradicts", "couldnt_check",
                                  "stale_link"])
def test_each_card_kind_names_topic_issue_context_options(repo: Path, kind: str) -> None:
    text = drawn(repo, card(kind))
    lines = text.splitlines()
    assert lines[0] == "Pages load fast"                                # the topic
    assert lines[1] == "it asks for a thing you did not say"            # the issue
    assert "You said: pages should load faster" in lines                # the context
    numbered = [line.strip() for line in lines if line.strip()[:2] in ("1.", "2.", "3.")]
    first = "1. Keep it (recommended)" if kind in ("couldnt_check", "stale_link") else "1. Keep it"
    assert numbered == [first, "2. Drop it", "3. Reword it"]            # no nudge on a check


def test_a_card_without_evidence_or_resolutions_renders_what_it_has(repo: Path) -> None:
    text = drawn(repo, card("couldnt_check", evidence="", resolutions=()))
    assert text.splitlines() == ["Pages load fast", "it asks for a thing you did not say"]


def test_owner_text_passes_both_scanners(repo: Path, write_record) -> None:
    from plumb.understand import cardstore, judge

    ids = make_world(repo, write_record, 3)
    job = judge.build(open_core(repo), SESSION, records=ids[1:])
    applied = judge.apply(open_core(repo), job, verdict_answer(
        (ids[1], "beyond", 0.9), (ids[2], "contradicts", 0.9),
        beyond={ids[1]: ["SR-002 says more than you did"]},
        contradicts={ids[2]: ["SR-003 EX-1 conflicts with SR-001 EX-1"]}))
    cardstore.save(repo, SESSION, applied.cards)
    out = parts(repo)
    assert not out.cards                                  # SR-152: lines, not cards
    for text in out.cards:
        assert owner_level(text) == [], text
    for kind in ("clarify", "trial", "beyond", "contradicts", "couldnt_check", "stale_link"):
        assert owner_level(drawn(repo, card(kind))) == [], kind


def test_stop_budget_holds(repo: Path, write_record) -> None:
    """The summary fits the stop hook's 1400 ms: the minimum of several runs, 0.9 of the
    budget (as tests/host/test_hook_perf.py does)."""
    make_world(repo, write_record, 24)
    runs = []
    for _ in range(3):
        started = time.perf_counter()
        parts(repo)
        runs.append(time.perf_counter() - started)
        (repo / ".plumb" / "session" / SESSION / "told.json").unlink(missing_ok=True)
    assert min(runs) < 1.4 * 0.9
    # a deadline already passed still gives an answer and nothing heavy
    from plumb.understand import summary

    expired = HookContext("stop", {}, repo, SESSION, Deadline(0))
    summary.stop_parts(expired, open_core(repo), {"turn_start": time.time() - 3600})


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
    assert "did not finish" in line and "try again" in line
    assert owner_level(line) == []
    assert job.id not in line
    for step in ("dispatch", "schema", "needs", "run", "timeout"):
        assert f"({step})" not in line
    assert owner_text.GATE_BUILD_ANYWAY in line and owner_text.GATE_WAIT in line


def test_a_failed_clarify_job_asks_to_build_without_the_check(repo: Path,
                                                              engine_standins) -> None:
    from plumb.understand import files, ledger, summary

    path = files.results_dir(repo, SESSION) / "clarify-0000000000000001.json"
    files.write_json_atomic(files.jobs_dir(repo, SESSION) / "clarify-0000000000000001.json",
                            {"v": 1, "id": "clarify-0000000000000001", "kind": "clarify",
                             "session": SESSION, "schema": "clarify.v1", "needs": None,
                             "inputs": {"message": {"digest": "sha256:abc", "text": "add a thing"}},
                             "inputs_digest": ""})
    files.write_json_atomic(path, {"v": 1, "job": "clarify-0000000000000001", "status": "error",
                                   "answer": None, "error": {"step": "run", "message": "down"},
                                   "model": "", "dispatcher": "fake", "started": "t",
                                   "finished": "t", "run_s": 0})
    # a result counts when the worker wrote it (the real queue looks for its ledger entry)
    ledger.record(repo, SESSION, "clarify-0000000000000001")
    line = "\n".join(summary.stop_parts(context(repo), open_core(repo), {}).cards)
    assert owner_text.GATE_BUILD_ANYWAY in line and owner_text.GATE_WAIT in line
    assert '"add a thing"' in line and "(run)" not in line


def stale_link(repo: Path, write_record) -> None:
    """SR-001#0 is a link that is stale now (a card of a link that is current or gone is
    withdrawn, SR-161)."""
    from plumb.contracts import Target

    make_world(repo, write_record, 1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("a = 1\n", encoding="utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    (repo / "src" / "calc.py").write_text("a = 2\n", encoding="utf-8")


def test_stale_link_card_rendered_by_the_summary_exactly_once(repo: Path, write_record) -> None:
    """SR-111 EX-5 carried over: the adapter feeds the summary, which renders it once."""
    stale_link(repo, write_record)
    path = repo / ".plumb" / "session" / SESSION / "stale_cards.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "link": "SR-001#0", "record": "SR-001", "path": "src/calc.py", "topic": "Add multiply",
        "issue": "the code changed after you confirmed it",
        "options": ["keep it as is", "reword the requirement", "undo the change"],
        "consequences": ["keeps both", "rewords it to the code", "puts the code back"],
        "why": "the change is what you asked for", "recommended": 1, "turn": 3,
        "status": "open"}]), encoding="utf-8")
    out = parts(repo)
    (line,) = out.cards
    assert line.count("Add multiply") == 1
    assert "the change is what you asked for" in line                # why, as the context
    assert "1. reword the requirement (recommended) - rewords it to the code" in line
    assert "2. keep it as is - keeps both" in line
    assert parts(repo).cards == out.cards                # every stop shows it while it is open


@pytest.mark.sr("SR-116")
def test_an_incomplete_stale_card_is_not_offered_but_stays_open(repo: Path,
                                                                write_record) -> None:
    """SR-116 EX-3: a card missing what its options do or why one is recommended is not
    offered; the owner is told cards wait for the agent, and the card stays open."""
    stale_link(repo, write_record)
    path = repo / ".plumb" / "session" / SESSION / "stale_cards.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "link": "SR-001#0", "record": "SR-001", "path": "src/calc.py", "topic": "Add multiply",
        "issue": "the code changed", "options": ["keep it", "undo it"], "recommended": 0,
        "turn": 3, "status": "open"}]), encoding="utf-8")
    (line,) = parts(repo).cards
    assert line == owner_text.FULL_INCOMPLETE.format(n=1)
    assert "Add multiply" not in line
    assert json.loads(path.read_text("utf-8"))[0]["status"] == "open"
