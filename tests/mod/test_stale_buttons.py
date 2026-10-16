"""SR-116: a stale-link card is drawn with a button per option, each with what it does and
leaves undone; a press on one is a recorded owner choice, never a repin or a confirmation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mod.helpers import DIGEST, KEY, SESSION, run_mod
from understand.test_read_job import make_core, record_text

from plumb.contracts import CardState, ClarifyQuestion
from plumb.mod import offers

pytestmark = pytest.mark.sr("SR-267")

OPTIONS = ["keep it as is", "reword the requirement", "undo the change"]
CONSEQUENCES = ["keeps the code; leaves the requirement unchecked",
                "rewords SR-001; leaves the code as it is", "reverts the code"]
ENTRY = {"link": "SR-001#0", "record": "SR-001", "path": "src/calc.py", "topic": "Add multiply",
         "issue": "the code changed after you confirmed it", "options": OPTIONS,
         "consequences": CONSEQUENCES, "recommended": 1, "turn": 1, "status": "open"}


@pytest.fixture
def core(repo: Path, write_record):
    core = make_core(repo, write_record, [record_text(1)])
    path = core.root / ".plumb" / "session" / SESSION / "stale_cards.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([ENTRY]), encoding="utf-8")
    return core


def _draw(core, monkeypatch, capsys) -> dict:
    assert run_mod(monkeypatch, capsys, core.root, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, answer, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0
    (card,) = [c for c in answer["cards"] if c["id"] == "stale:SR-001#0"]
    return card


def test_a_stale_card_is_drawn_with_a_button_per_option_and_its_consequence(
        core, monkeypatch, capsys) -> None:
    (offer,) = _draw(core, monkeypatch, capsys)["offers"]
    shown = [(b["label"], b["consequence"]) for b in offer["buttons"]]
    assert shown[:3] == [(OPTIONS[1], CONSEQUENCES[1]), (OPTIONS[0], CONSEQUENCES[0]),
                         (OPTIONS[2], CONSEQUENCES[2])]          # the recommended one first
    assert [label for label, _ in shown[3:]] == ["Ask for a change", "Leave open"]


def test_a_press_on_a_stale_option_is_a_recorded_choice_and_confirms_nothing(
        core, monkeypatch, capsys) -> None:
    (offer,) = _draw(core, monkeypatch, capsys)["offers"]
    code, result, _ = run_mod(monkeypatch, capsys, core.root, "press", "--offer",
                              offer["offer_id"], "--choice", "0", stdin={"key": KEY})
    assert code == 0 and result["label"] == OPTIONS[1]
    assert result["confirmed"] == [] and result["rejected"] == []


def test_a_question_with_no_choices_falls_back_to_the_card_resolutions() -> None:
    card = CardState(id="stale:x", kind="stale_link", resolutions=("a", "b"))
    question = ClarifyQuestion(id="stale:x#1", resolutions=("a", "b"))
    assert [b.label for b in offers.buttons(card, question)][:2] == ["a", "b"]
