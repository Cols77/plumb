"""SR-172: several open cards that hinge on one principle are asked once; a confirmed decision
on it settles each of them from its words, told in the plumb line and undoable. The model is
stubbed."""

from __future__ import annotations

import time
import types
from pathlib import Path
from typing import Any

import pytest

from plumb import stale
from plumb.api import open_core
from plumb.hosts.claude_code.hookio import Deadline, HookContext
from plumb.understand import cardstore, summary, tidy, worker
from understand.test_judge_job import SESSION, log_prompt, requirement_text

pytestmark = pytest.mark.sr("SR-219")

DECIDES = "the owner's answer is what the owner typed or pressed, never the agent's reading"
CODE = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def world(repo: Path, write_record, engine_standins):
    write_record(repo, requirement_text(1, "Answers", DECIDES))
    write_record(repo, requirement_text(2, "Adds", "add returns the sum."))
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    from plumb.contracts import Target

    (repo / "src" / "other.py").write_text(CODE, "utf-8")
    for name in ("calc", "other"):
        open_core(repo).add_link("SR-002", "implemented_by", Target(path=f"src/{name}.py"))
        (repo / "src" / f"{name}.py").write_text(CODE.replace("a + b", "b + a"), "utf-8")
    for n in (1, 2):
        stale.add_card(repo, SESSION, link=f"SR-002#{n - 1}", record="SR-002", path="src/calc.py",
                       topic=f"Adds {n}", issue="the code changed", options=["keep", "undo"])
    return engine_standins


def _run(repo: Path, confirmed: bool = True) -> Any:
    core = open_core(repo)
    core.status = lambda ids: {i: types.SimpleNamespace(
        confirmation="confirmed" if confirmed else "proposed", superseded_by=None) for i in ids}
    tidy.enqueue(core, SESSION)
    worker.run_once(core, SESSION)
    return open_core(repo)


PRINCIPLE = {"question": "What counts as your answer?", "options": ["Your words", "Any reading"],
             "cards": ["stale:SR-002#0", "stale:SR-002#1"]}


def _turn_end(repo: Path) -> str:
    ctx = HookContext("stop", {}, repo, SESSION, Deadline(300))
    return "\n".join(summary.stop_parts(ctx, open_core(repo), {"turn_start": time.time() - 60}).cards)


def test_ex1_cards_hinging_on_one_principle_are_asked_once_and_not_drawn(
        repo: Path, world) -> None:
    world.dispatcher.script = {"tidy": {"verdicts": [], "principles": [PRINCIPLE]}}
    _run(repo)
    (card,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "principle"]
    assert card.topic == "What counts as your answer?" and "Adds 1; Adds 2" in card.issue
    assert set(cardstore.grouped(repo, SESSION)) == set(PRINCIPLE["cards"])
    shown = _turn_end(repo)
    assert "What counts as your answer?" in shown and "the code changed" not in shown


def test_a_lone_card_is_no_principle(repo: Path, world) -> None:
    world.dispatcher.script = {"tidy": {"verdicts": [], "principles": [
        {**PRINCIPLE, "cards": ["stale:SR-002#0"]}]}}
    _run(repo)
    assert cardstore.grouped(repo, SESSION) == {}


SETTLE = [{"card": "stale:SR-002#0", "action": "withdraw", "decision": "SR-001", "quote": DECIDES},
          {"card": "stale:SR-002#1", "action": "stays"}]


def _grouped(repo: Path) -> None:
    cardstore.group(repo, SESSION, "principle:x", PRINCIPLE["cards"])


def test_ex2_a_confirmed_decision_settles_each_card_and_the_line_counts_them(
        repo: Path, world) -> None:
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": [
        SETTLE[0], {"card": "stale:SR-002#1", "action": "repin", "decision": "SR-001",
                    "quote": DECIDES}]}}
    core = _run(repo)
    assert cardstore.load(repo, SESSION) == []
    assert [e.payload["action"] for e in core.log_read("events", ["card-settled"])] == [
        "withdraw", "repin"]
    assert "Settled from your decision: 1 withdrawn, 1 repinned" in _turn_end(repo)


@pytest.mark.sr("SR-335")
def test_ex2_a_record_only_the_agent_wrote_settles_nothing(repo: Path, world) -> None:
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": [SETTLE[0]]}}
    _run(repo, confirmed=False)
    assert len(cardstore.load(repo, SESSION)) == 2


@pytest.mark.sr("SR-335")
def test_ex1_a_decision_quoting_the_owners_answer_settles_before_approval(
        repo: Path, world, write_record) -> None:
    log_prompt(repo, f"Yes: {DECIDES}.")
    write_record(repo, "---\nid: DEC-001\ntitle: What counts as your answer\nquestion: What "
                 f"counts?\nchosen: Your words\nquote: {DECIDES}\nalternatives:\n- Any reading\n"
                 "matters: true\nlinks:\n- kind: decides\n  to: SR-002\n---\n")
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": [
        {**SETTLE[0], "decision": "DEC-001", "quote": "What counts as your answer"}]}}
    _run(repo, confirmed=False)
    assert [c.id for c in cardstore.load(repo, SESSION)] == ["stale:SR-002#1"]


def test_ex3_a_card_the_model_cannot_settle_stays_with_one_line(repo: Path, world) -> None:
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": SETTLE}}
    _run(repo)
    _run(repo)      # a second reading says it once only
    assert [c.id for c in cardstore.load(repo, SESSION)] == ["stale:SR-002#1"]
    assert "1 withdrawn, 1 could not be settled and stay open" in _turn_end(repo)


def test_ex4_undo_puts_the_card_and_the_reworded_statement_back(repo: Path, world) -> None:
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": [
        {"card": "stale:SR-002#0", "action": "reword", "decision": "SR-001", "quote": DECIDES,
         "wording": "add returns the total."}]}}
    core = _run(repo)
    assert core.index()["SR-002"].fields["statement"] == "add returns the total."
    assert tidy.undo(core, SESSION, "stale:SR-002#0")
    core = open_core(repo)
    assert core.index()["SR-002"].fields["statement"] == "add returns the sum."
    assert "stale:SR-002#0" in [c.id for c in cardstore.load(repo, SESSION)]
    assert [s.state for s in core.link_states(["SR-002"]) if s.link.id == "SR-002#0"] == ["stale"]
    assert not tidy.undo(core, SESSION, "stale:SR-002#0")


def test_ex4_an_undone_settlement_stays_open_on_the_next_tidy_run(repo: Path, world) -> None:
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": [SETTLE[0]]}}
    core = _run(repo)
    assert tidy.undo(core, SESSION, "stale:SR-002#0")
    assert "stale:SR-002#0" not in cardstore.grouped(repo, SESSION)
    _run(repo)
    cardstore.group(repo, SESSION, "principle:x", ["stale:SR-002#0"])   # asked again: still kept
    _run(repo)
    assert "stale:SR-002#0" in [c.id for c in cardstore.load(repo, SESSION)]


def test_ex4_the_undo_entry_reopens_a_settled_card(repo: Path, world, capsys) -> None:
    _grouped(repo)
    world.dispatcher.script = {"tidy": {"verdicts": [], "settlements": [SETTLE[0]]}}
    _run(repo)
    argv = ["stale:SR-002#0", "--root", str(repo), "--session", SESSION]
    assert tidy.run("undo", argv) == 0 and "is open again" in capsys.readouterr().out
    assert tidy.run("undo", argv) == 1
