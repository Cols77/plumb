"""SP7 slice 3 x slices 4/7: what the end of a turn draws and what the panel draws agree.

- DEC-034 at the turn end: a card the owner pressed Leave open on is not drawn again at the end
  of a turn until a record it asks about changes, and stays listed under what awaits the owner
  (``summary._repeats_at_turn_end``).
- The cards the stop hook builds (a regression, a decision, a conflict, the records the turn
  proposed) are not in ``cards.json``: the panel draws them from the last turn end with their
  full content (SR-116) and offers Ask for a change and Leave open on them; Leave open holds
  until a record the card shows changes."""

from __future__ import annotations

import types
from pathlib import Path

import pytest
from mod.helpers import DIGEST, KEY, SESSION, kinds, run_mod, sample_card
from understand.test_read_job import make_core, open_card, record_text

from plumb.api import open_core
from plumb.understand import cards as card_text
from plumb.understand import summary

pytestmark = pytest.mark.sr("SR-209")

ASK_CHANGE, LEAVE_OPEN = 0, 1          # a stop-hook card's buttons, in order


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(n) for n in range(1, 3)])


def _ctx() -> types.SimpleNamespace:
    return types.SimpleNamespace(session_id=SESSION, deadline=None, extra={})


def _turn_end(core, extra=()) -> list[str]:
    fresh = open_core(core.root)          # the stop hook opens the records as they are now
    parts = summary.stop_parts(_ctx(), fresh, {"turn_start": 1000.0}, extra=list(extra))
    return list(parts.cards)


def _hello(monkeypatch, capsys, core) -> None:
    assert run_mod(monkeypatch, capsys, core.root, "hello",
                   stdin={"key_digest": DIGEST})[0] == 0


def _draw(monkeypatch, capsys, core) -> dict:
    code, answer, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0
    return {c["id"]: c for c in answer["cards"]}


def _press(monkeypatch, capsys, core, offer: str, choice: int):
    return run_mod(monkeypatch, capsys, core.root, "press", "--offer", offer, "--choice",
                   str(choice), stdin={"key": KEY})


def _edit(root: Path, n: int = 1) -> None:
    path = root / ".plumb" / "requirements" / f"SR-{n:03d}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(f"statement {n}",
                                                             f"statement {n}, reworded"),
                    encoding="utf-8")


def test_a_card_left_open_is_not_drawn_at_turn_end_until_its_record_changes(
        core, monkeypatch, capsys) -> None:
    open_card(core, sample_card(core, "SR-001"))
    _hello(monkeypatch, capsys, core)
    offer = _draw(monkeypatch, capsys, core)["card:SR-001"]["offers"][0]
    assert any("Requirement 1" in c for c in _turn_end(core))
    leave = next(b["index"] for b in offer["buttons"] if b["answer"] == "open")
    assert _press(monkeypatch, capsys, core, offer["offer_id"], leave)[0] == 0
    assert not any("Requirement 1" in c for c in _turn_end(core))
    # still listed under what awaits the owner
    card = _draw(monkeypatch, capsys, core)["card:SR-001"]
    assert card["status"] == "left_open" and card["repeats"] is False
    _edit(core.root)
    assert any("Requirement 1" in c for c in _turn_end(core))


def test_a_stop_hook_card_is_drawn_by_the_panel_in_full_with_leave_open(
        core, monkeypatch, capsys) -> None:
    proposed = card_text.test_changed_card(core.index()["SR-001"], ["tests/test_x.py"], turn=1000)
    drawn_text = _turn_end(core, [proposed])
    assert any(proposed.topic in c for c in drawn_text)
    _hello(monkeypatch, capsys, core)
    card = _draw(monkeypatch, capsys, core)[proposed.id]
    assert card["kind"] == "test_changed" and card["repeats"] is True
    assert card["content"]["id"] == proposed.id and card["content"]["options"]
    (offer,) = card["offers"]
    assert [b["answer"] for b in offer["buttons"]] == ["change", "open"]
    code, answer, _ = _press(monkeypatch, capsys, core, offer["offer_id"], LEAVE_OPEN)
    assert code == 0 and answer["status"] == "left_open" and answer["confirmed"] == []
    assert "approval" not in kinds(core.root) and "card-press" in kinds(core.root)
    # DEC-034: not drawn at the next turn end, still listed as awaiting
    assert not any(proposed.topic in c and "changed since you confirmed it" in c for c in _turn_end(core))
    listed = _draw(monkeypatch, capsys, core)[proposed.id]
    assert listed["status"] == "left_open" and listed["repeats"] is False
    # until the record it shows changes: it is drawn again
    _edit(core.root)
    assert any("changed since you confirmed it" in c for c in _turn_end(core))


def test_ask_for_a_change_on_a_stop_hook_card_prefills_and_confirms_nothing(
        core, monkeypatch, capsys) -> None:
    proposed = card_text.test_changed_card(core.index()["SR-001"], ["tests/test_x.py"], turn=1000)
    _turn_end(core, [proposed])
    _hello(monkeypatch, capsys, core)
    (offer,) = _draw(monkeypatch, capsys, core)[proposed.id]["offers"]
    code, answer, _ = _press(monkeypatch, capsys, core, offer["offer_id"], ASK_CHANGE)
    assert code == 0 and answer["status"] == "change_requested"
    assert answer["prefill"] and answer["confirmed"] == []
    assert "approval" not in kinds(core.root)
    assert _press(monkeypatch, capsys, core, offer["offer_id"], 5)[0] == 2
