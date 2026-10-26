"""SR-118: the trial cards the owner presses carry the words behind their record: ``plumb mod
draw`` (the panel), the stop hook's read-back and the end-of-turn summary all show them, and a
search of past transcripts confirms nothing by itself (what it finds and how it is judged is
``test_recover_quotes``). Fake models and a temp transcript directory only."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.understand import recover
from understand.test_judge_cascade import world  # noqa: F401 - pytest fixture
from understand.test_judge_job import intent_text
from understand.test_judge_questions import _transcript, answer, applied_on, asking, written
from understand.test_recover_quotes import (  # noqa: F401 - pytest fixtures
    Dispatcher,
    Jev,
    _cascade,
    _picks,
    project,
    transcripts,
)

pytestmark = pytest.mark.sr("SR-249")

SPAN = "Keep each card to one screen at most"


def _found_short(core, transcripts: Path) -> None:
    sonnet = Dispatcher("sonnet", _picks("cards should be short", SPAN))
    outcome = recover.recover(core, ["INT-009"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("cards should be short"), sonnet))
    assert outcome.errors == [] and [f.status for f in outcome.findings] == ["found"]


def _own(root: Path, session: str, *ids: str) -> list:
    from plumb.understand import cardstore, trial

    core = open_core(root)
    cards = [trial.card(core, trial.Candidate(core.index()[rid], 0.9, {})) for rid in ids]
    cardstore.save(root, session, [*cardstore.own_cards(root, session), *cards])
    return cards


def test_the_stop_summary_and_read_back_show_the_records_words(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code.hookio import Deadline, HookContext
    from plumb.understand import summary

    monkeypatch.chdir(project)
    session = "sess-stop"
    core = open_core(project)
    _found_short(core, transcripts)
    _own(project, session, "INT-009")

    ctx = HookContext("stop", {}, project, session, Deadline(30_000))
    parts = summary.stop_parts(ctx, open_core(project), {"turn_start": time.time() - 3600})
    assert '"Keep each card to one screen at most" (4 Oct)' in "\n".join(parts.cards)


def test_ex1_a_transcript_match_is_quoted_with_its_date_and_approves_nothing(
        world: Path, write_record, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
        tmp_path: Path) -> None:
    """SR-249 EX-1, without cards: the judge question quotes the found words with their date,
    and the older record stays unconfirmed with no approval logged."""
    write_record(world, intent_text(2, "Cache the front page", "Cache the front page"))
    _transcript(world, monkeypatch, tmp_path, "Cache the front page, please")
    applied_on(world, ["INT-002"], answer(("INT-002", "supported"), questions=[
        asking("INT-002", request={})]))
    (question,) = written(world)
    assert 'You said on 4 Oct: "Cache the front page"' in question["question"]
    core = open_core(world)
    assert core.status()["INT-002"].confirmation != "confirmed"
    assert not [e for e in core.events() if e.kind == "approval"]
