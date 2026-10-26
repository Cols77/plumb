"""CAPTURE SR-097: a short answer is judged together with the question it answered."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from capture_helpers import run

from plumb.api import open_core
from plumb.capture.records import is_short_answer
from plumb.understand.claim import claim

pytestmark = pytest.mark.sr("SR-212")

QUESTION = "Mostly in the background, or a checkpoint every turn? A. Mostly in the " \
           "background, B. A checkpoint every turn"


def capture(repo: Path, intent: dict) -> int:
    path = repo / "capture.json"
    path.write_text(json.dumps({"intent": intent}), encoding="utf-8")
    return run(repo, "capture", "--file", str(path))


def only_intent(repo: Path):
    core = open_core(repo)
    return core, next(r for r in core.index().values() if r.kind == "intent")


def test_claim_premise_holds_the_question_and_the_answer(repo: Path, capsys) -> None:
    assert capture(repo, {"quote": "A", "readback": "run in the background",
                          "question": QUESTION}) == 0
    core, record = only_intent(repo)
    kind, premise, _ = claim(core.index(), record)
    assert kind == "intent-readback"
    assert QUESTION in premise and premise.endswith("A") and premise != "A"


def test_intent_command_stores_the_question(repo: Path, capsys) -> None:
    assert run(repo, "intent", "--quote", "yes", "--readback", "go ahead",
               "--question", "Should it run in the background?") == 0
    core, record = only_intent(repo)
    assert record.fields["question"] == "Should it run in the background?"
    assert claim(core.index(), record)[1] == "Should it run in the background?\nyes"


def test_short_answer_without_question_warns_and_records(repo: Path, capsys) -> None:
    assert capture(repo, {"quote": "A", "readback": "run in the background"}) == 0
    out = capsys.readouterr().out
    assert "short answer" in out and "question" in out
    core, record = only_intent(repo)
    assert "question" not in record.fields
    assert claim(core.index(), record)[1] == "A"


def test_intent_command_warns_on_a_bare_short_answer(repo: Path, capsys) -> None:
    assert run(repo, "intent", "--quote", "ok", "--readback", "fine") == 0
    assert "short answer" in capsys.readouterr().out
    assert any(r.kind == "intent" for r in open_core(repo).index().values())


def test_full_sentence_quote_is_unchanged(repo: Path, capsys) -> None:
    sentence = "run mostly in the background please"
    assert capture(repo, {"quote": sentence, "readback": "background",
                          "question": QUESTION}) == 0
    out = capsys.readouterr().out
    assert "short answer" not in out
    core, record = only_intent(repo)
    assert claim(core.index(), record)[1] == sentence


def test_full_sentence_without_question_does_not_warn(repo: Path, capsys) -> None:
    assert capture(repo, {"quote": "add a multiply command", "readback": "multiply"}) == 0
    assert "short answer" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "quote", ["A", "b.", "Yes", "ok!", "go ahead", "Sounds good", "A / B", "A+B"]
)
def test_short_answers_are_recognised(quote: str) -> None:
    assert is_short_answer(quote)


@pytest.mark.parametrize("quote", ["add a multiply command", "yes but only on Fridays", ""])
def test_sentences_are_not_short_answers(quote: str) -> None:
    assert not is_short_answer(quote)
