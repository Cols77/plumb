"""R5: owner-only settings, Undo and the release of a failed check change only by the typed
command or a button, never by the reader's reading of prose (SR-101 EX-8, SR-105 EX-6,
SR-106 EX-4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.fakes import as_worker, owner_level
from understand.test_read_apply import entries_of, write_applied
from understand.test_read_job import SESSION, log_prompt, make_core, open_card, record_text

from plumb.api import open_core
from plumb.contracts import CardState, ClarifyQuestion
from plumb.present import owner_text
from plumb.understand import cardstore, effects, read

pytestmark = pytest.mark.sr("SR-101")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(2), record_text(3)])


def prose(core, card: CardState, message: str, item: str, evidence: str):
    open_card(core, card)
    digest = log_prompt(core, message)
    job = read.build(core, SESSION, message={"digest": digest, "text": message})
    entry = {"id": item, "hash": "", "answer": "accepted", "evidence": evidence,
             "confidence": 0.99}
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [entry]})
    write_applied(core, applied)
    return open_core(core.root), applied


def test_ex8_prose_turn_settling_on_changes_nothing_and_names_the_command(core) -> None:
    offer = CardState(id="o1", kind="settle_offer", topic="intent read-backs",
                      questions=(ClarifyQuestion(id="q", text="turn settling on for intents?"),))
    after, applied = prose(core, offer, "turn settling on", "o1/q", "turn settling on")
    assert entries_of(after, "settle-config") == []
    assert [c.status for c in cardstore.load(after.root, SESSION)] == ["open"]
    (reply,) = applied.notes
    assert "/plumb settle on intent" in reply and "button" in reply
    assert not any(e["kind"] not in ("read-entry", "prompt") for e in applied.entries)


def test_prose_undo_that_names_the_button(core) -> None:
    settled = CardState(id="s1", kind="settled_item", topic="Add multiply",
                        questions=(ClarifyQuestion(id="q", text="settled from your words",
                                                   record="SR-002"),))
    after, applied = prose(core, settled, "undo that", "s1/q", "undo that")
    assert entries_of(after, "revocation") == []
    (reply,) = applied.notes
    assert "button" in reply and "/plumb undo SR-002" in reply
    assert [c.status for c in cardstore.load(after.root, SESSION)] == ["open"]


def test_settle_offer_card_is_owner_only(core) -> None:
    assert {"settle_offer", "settled_item"} <= set(effects.NO_EFFECT)
    flagged = CardState(id="f1", kind="clarify", topic="x", owner_only=True,
                        questions=(ClarifyQuestion(id="q", text="release the check?"),))
    after, applied = prose(core, flagged, "yes release it", "f1/q", "yes release it")
    assert applied.notes and applied.cards == ()
    assert [c.status for c in cardstore.load(after.root, SESSION)] == ["open"]


def test_typed_command_reply_and_owner_only_reply_pass_the_owner_level_scan() -> None:
    replies = [
        owner_text.TYPED_CONFIRMED.format(titles="Pick a store, Add multiply"),
        owner_text.TYPED_NEEDS_IDS,
        owner_text.OWNER_ONLY_REPLY.format(action="switch settling on or off",
                                           command="/plumb settle on intent"),
        owner_text.OWNER_ONLY_REPLY.format(action="undo anything", command="/plumb undo SR-002"),
    ]
    for reply in replies[:3]:
        assert owner_level(reply) == []
    # the undo reply names the record by its ID inside the typed command, as typed commands do
    assert [o for o in owner_level(replies[3]) if o != "SR-002"] == []
