"""SP8 3.2 item 6: ``cardstore`` loads the open entries of STALE's ``stale_cards.json`` as
``stale_link`` cards (same topic, issue and resolutions), read-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb.understand import cardstore

pytestmark = pytest.mark.sr("SR-111")


def _write(root: Path, entries: list[dict]) -> Path:
    path = root / ".plumb" / "session" / "s1" / "stale_cards.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


ENTRY = {"link": "SR-001#0", "record": "SR-001", "path": "src/calc.py",
         "topic": "Add multiply", "issue": "the code changed after you confirmed it",
         "options": ["keep it as is", "reword the requirement", "undo the change"],
         "recommended": 1, "turn": 3, "status": "open"}


def test_open_entry_becomes_a_stale_link_card(tmp_path: Path) -> None:
    _write(tmp_path, [ENTRY])
    (card,) = cardstore.load(tmp_path, "s1")
    assert card.kind == "stale_link"
    assert card.topic == ENTRY["topic"]
    assert card.issue == ENTRY["issue"]
    assert set(card.resolutions) == set(ENTRY["options"])
    assert card.resolutions[0] == "reword the requirement"   # the recommended first
    assert card.status == "open"
    assert card.turn == 3


def test_resolved_entries_are_not_cards(tmp_path: Path) -> None:
    _write(tmp_path, [{**ENTRY, "status": "resolved"}])
    assert cardstore.load(tmp_path, "s1") == []


def test_adapter_never_writes_the_stale_file(tmp_path: Path) -> None:
    path = _write(tmp_path, [ENTRY])
    before = path.read_bytes()
    cards = cardstore.load(tmp_path, "s1")
    cardstore.save(tmp_path, "s1", cards)
    assert path.read_bytes() == before
    own = json.loads((tmp_path / ".plumb" / "session" / "s1" / "cards.json")
                     .read_text(encoding="utf-8"))
    assert own == []   # stale-link cards are not copied into cards.json


def test_own_cards_round_trip_with_stale_ones_alongside(tmp_path: Path) -> None:
    from plumb.contracts import CardState, ClarifyQuestion

    _write(tmp_path, [ENTRY])
    mine = CardState(id="c1", kind="clarify", topic="t", issue="i", evidence="e",
                     resolutions=("a", "b"),
                     questions=(ClarifyQuestion(id="q1", text="which?", resolutions=("a",)),),
                     turn=2)
    cardstore.save(tmp_path, "s1", [mine])
    loaded = cardstore.load(tmp_path, "s1")
    assert [c.kind for c in loaded] == ["clarify", "stale_link"]
    assert loaded[0] == mine


def test_missing_or_broken_files_give_no_cards(tmp_path: Path) -> None:
    assert cardstore.load(tmp_path, "s1") == []
    path = tmp_path / ".plumb" / "session" / "s1" / "stale_cards.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert cardstore.load(tmp_path, "s1") == []
