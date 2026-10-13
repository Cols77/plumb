"""R5: a record is taken back, and a failed check released, only by the typed command or a
button, never by the reader's reading of prose (SR-101 EX-8; SR-135 EX-3: the typed undo is
done by the prompt hook, see test_one_judge)."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.fakes import as_worker
from understand.test_read_apply import entries_of, write_applied
from understand.test_read_job import SESSION, log_prompt, make_core, open_card, record_text

from plumb.api import open_core
from plumb.present import owner_text
from plumb.understand import read, trial

pytestmark = pytest.mark.sr("SR-101")


@pytest.fixture
def core(repo: Path, write_record):
    return make_core(repo, write_record, [record_text(2), record_text(3)])


def test_ex8_prose_undo_takes_nothing_back(core) -> None:
    card = trial.card(core, trial.Candidate(core.index()["SR-002"], 0.9, {}))
    open_card(core, card)
    digest = log_prompt(core, "undo that")
    job = read.build(core, SESSION, message={"digest": digest, "text": "undo that"})
    entry = {"id": f"{card.id}/{card.questions[0].id}", "hash": "", "answer": "open",
             "evidence": "undo that", "confidence": 0.99}
    with as_worker(core.root, SESSION):
        applied = read.apply(core, job, {"entries": [entry]})
    write_applied(core, applied)
    after = open_core(core.root)
    assert entries_of(after, "revocation") == [] and entries_of(after, "approval") == []


def test_typed_command_replies_pass_the_owner_level_scan() -> None:
    from understand.fakes import owner_level

    for reply in (owner_text.TYPED_CONFIRMED.format(titles="Pick a store, Add multiply"),
                  owner_text.TYPED_NEEDS_IDS):
        assert owner_level(reply) == []
