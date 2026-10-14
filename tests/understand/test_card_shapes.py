"""SR-129, SR-135 EX-2, SR-145 EX-4 (INT-036, DEC-039): a card is a read-back or a choice, one
renderer draws both, an option with no consequence is printed alone, and nothing of plumb's
mechanics reaches the owner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from plumb.api import open_core
from plumb.contracts import CardState, Choice, ClarifyQuestion
from plumb.understand import cardstore, clarify, fullcard, gate, worker

pytestmark = [pytest.mark.sr("SR-129"), pytest.mark.sr("SR-145")]

SESSION = "s1"
SR = ("---\nid: SR-001\ntitle: Export users as CSV\nfeature: FEAT-001\n"
      "statement: export the user list as CSV\n"
      "examples:\n- id: EX-1\n  given: 2 users\n  when: exported\n  then: 2 rows\n---\n")
READBACK = {"proposal": "Work in a worktree. Merge it at the end.",
            "will": [f"will {n}" for n in range(1, 6)],
            "wont": ["touch main", "rewrite history"],
            "assumptions": [f"assumption {n}" for n in range(1, 5)],
            "examples": ["example one", "example two", "example three"]}


def _asked(repo: Path, engine_standins: Any, answer: dict[str, Any]) -> tuple[Any, CardState]:
    core = open_core(repo)
    digest = log_prompt(repo, "do the findings above", session=SESSION)
    gate.close(repo, SESSION, digest, "your request is being checked")
    engine_standins.dispatcher.script = {"clarify": {
        "gap": bool(answer.get("gaps")), "intent": "yes", **answer}}
    assert clarify.build(core, SESSION, message={"digest": digest, "text": "do the findings"})
    worker.run_once(core, SESSION)
    core = open_core(repo)
    return core, [c for c in cardstore.own_cards(repo, SESSION) if c.status == "open"][0]


def test_ex1_a_readback_is_the_proposal_the_assumptions_and_one_wont(
        repo: Path, engine_standins) -> None:
    core, card = _asked(repo, engine_standins, {"gaps": [], "readback": READBACK})
    item = fullcard.content(core, card)
    assert item["wont"] == "touch main"
    assert item["assumptions"] == READBACK["assumptions"]
    text = fullcard.render(item)
    assert item["issue"] in text and text.count("Not doing:") == 1
    for left_out in ("will 1", "rewrite history", "example", "sha256", "clarify:", "INT-"):
        assert left_out not in text
    assert 1 <= item["issue"].count(".") <= 3


def test_ex2_a_choice_names_its_request_with_its_date_and_what_changes(
        repo: Path, engine_standins) -> None:
    gap = {"id": "way", "question": "Which way?", "blocking": True, "recommended": 1,
           "suggestions": ["the first way", "the second way"],
           "consequences": ["costs a day", "costs an hour"]}
    core, card = _asked(repo, engine_standins, {"gaps": [gap], "readback": READBACK})
    (choice,) = [c for c in cardstore.own_cards(repo, SESSION) if c.kind == "choice"]
    item = fullcard.content(core, choice)
    assert "your request of 20" in item["topic"]
    assert item["issue"] == "Which way?"
    assert [(o["text"], o["consequence"], o["recommended"]) for o in item["options"]] == [
        ("the second way", "costs an hour", False), ("the first way", "costs a day", False)]
    assert fullcard.lines(item)[-2:] == ["  1. the second way - costs an hour",
                                         "  2. the first way - costs a day"]


def test_ex3_plumb_text_shows_no_record_id_or_digest(repo: Path, write_record) -> None:
    write_record(repo, SR)
    card = CardState(
        id="beyond:x", kind="beyond", topic="Export users as CSV",
        issue="SR-001 EX-1 was changed; digest sha256:" + "ab" * 32,
        evidence='"my trial run settled it" ' + "0123456789abcdef" * 2,
        resolutions=("Keep it",), questions=(ClarifyQuestion(
            id="beyond:x#1", text="q", choices=(Choice(
                "Keep it", "accepted", consequence="It is confirmed with SR-001"),)),))
    text = fullcard.render(fullcard.content(open_core(repo), card))
    for word in ("SR-001", "sha256", "0123456789abcdef"):
        assert word not in text.replace('"my trial run settled it"', "")
    assert '"Export users as CSV"' in text and "confirmed" in text
    assert '"my trial run settled it"' in text          # the owner's quote is left as written


def test_ex3_plain_covers_slash_ids_nc_ids_plumb_words_and_empty_brackets(
        repo: Path, write_record) -> None:
    from plumb.understand.cards import plain

    write_record(repo, SR)
    index = open_core(repo).index()
    assert plain("as SR-001/EX-2 says", index) == 'as "Export users as CSV" (example 2) says'
    assert plain("per SR-001/A-1", index) == 'per "Export users as CSV" (assumption 1)'
    assert plain("NC-004 and IC-002", index) == "another record and another record"
    assert plain("the free trial settles nightly", index) == "the free trial settles nightly"
    assert plain("adds EX-5 about it", index) == "adds an example about it"
    assert plain("kept (sha256:" + "ab" * 32 + ")?", index) == "kept?"


def test_an_option_with_no_consequence_is_printed_alone_without_a_placeholder(
        repo: Path) -> None:
    card = CardState(id="couldnt:1", kind="couldnt_check", topic="t", issue="i",
                     resolutions=("Wait", "Build anyway"))
    text = fullcard.render(fullcard.content(open_core(repo), card))
    assert text.splitlines()[-2:] == ["  1. Wait (recommended)", "  2. Build anyway"]
    assert "not written" not in text


def test_sr145_ex4_a_card_with_no_diagram_has_no_diagram_line(repo: Path) -> None:
    plain = CardState(id="c:1", kind="choice", topic="t", issue="i", resolutions=("A", "B"))
    drawn = CardState(id="c:2", kind="choice", topic="t", issue="i", resolutions=("A", "B"),
                      diagram=".plumb/session/s1/diagrams/a.html")
    core = open_core(repo)
    assert not any(line.startswith("Diagram") for line in fullcard.lines(
        fullcard.content(core, plain)))
    assert fullcard.lines(fullcard.content(core, drawn))[0] == (
        "Diagram: .plumb/session/s1/diagrams/a.html (open it to see it)")


def test_the_blocking_question_ranks_before_its_read_back() -> None:
    from plumb.understand import cards

    read_back, question = CardState(id="a", kind="clarify"), CardState(id="b", kind="choice")
    assert [c.id for c in sorted([read_back, question], key=cards.kind_rank)] == ["b", "a"]


def test_ex3_ids_in_the_written_lines_never_reach_the_card(repo: Path, write_record) -> None:
    write_record(repo, SR)
    card = CardState(
        id="clarify:fbad43d46a42", kind="clarify", topic="Export", issue="Export the list.",
        evidence="Assumed: SR-001 wants CSV, and the card (clarify:806fcf02b27f) stays open\n"
                 "Not doing: change DEC-009 in any way")
    text = fullcard.render(fullcard.content(open_core(repo), card))
    assert "Export users as CSV" in text and "wants CSV" in text
    for left_out in ("SR-001", "DEC-009", "clarify:", "806fcf02b27f"):
        assert left_out not in text
