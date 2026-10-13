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
from understand.test_recover_quotes import (  # noqa: F401 - pytest fixtures
    Dispatcher,
    Jev,
    _cascade,
    _picks,
    project,
    transcripts,
)

pytestmark = pytest.mark.sr("SR-118")

SPAN = "Keep each card to one screen at most"
REWORDING = "You want a weekly digest by email."


def _found_short(core, transcripts: Path) -> None:
    sonnet = Dispatcher("sonnet", _picks("cards should be short", SPAN))
    outcome = recover.recover(core, ["INT-009"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("cards should be short"), sonnet))
    assert outcome.errors == [] and [f.status for f in outcome.findings] == ["found"]


def _misreads(core, transcripts: Path, span: str = "send me a digest every week") -> None:
    sonnet = Dispatcher("sonnet", _picks("digest", span, supports=False,
                                         reason="weekly, not daily"))
    opus = Dispatcher("opus", {"verdict": "misreads",
                               "explanation": "The record says daily; you asked for weekly.",
                               "proposed_wording": REWORDING})
    outcome = recover.recover(core, ["INT-020"], transcripts=transcripts,
                              cascade=_cascade(core, Jev("digest"), sonnet, opus))
    assert outcome.errors == [] and len(outcome.findings) == 1


def _own(root: Path, session: str, *ids: str) -> list:
    from plumb.understand import cardstore, trial

    core = open_core(root)
    cards = [trial.card(core, trial.Candidate(core.index()[rid], 0.9, {})) for rid in ids]
    cardstore.save(root, session, [*cardstore.own_cards(root, session), *cards])
    return cards


def _drawn(monkeypatch, capsys, root: Path) -> dict[str, dict]:
    from mod.helpers import DIGEST, KEY, run_mod

    assert run_mod(monkeypatch, capsys, root, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, drawn, _ = run_mod(monkeypatch, capsys, root, "draw", stdin={"key": KEY})
    assert code == 0
    return {card["id"]: card for card in drawn["cards"]}


def test_mod_draw_shows_the_records_words_and_confirms_nothing(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    from mod.helpers import SESSION

    core = open_core(project)
    _found_short(core, transcripts)
    _misreads(core, transcripts)
    short, digest = _own(project, SESSION, "INT-009", "INT-020")
    drawn = _drawn(monkeypatch, capsys, project)

    # INT-036: a trial card is the read-back of one record with the words behind it
    assert drawn[short.id]["content"]["context"] == [
        '"Keep each card to one screen at most" (4 Oct)', "Is this what you meant?"]
    assert drawn[digest.id]["content"]["context"]
    # shown, never trusted: drawing the cards confirms nothing
    statuses = open_core(project).status()
    assert statuses["INT-009"].confirmation == statuses["INT-020"].confirmation == "proposed"


def test_the_stop_summary_and_read_back_show_the_records_words(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import stop
    from plumb.hosts.claude_code.hookio import Deadline, HookContext
    from plumb.understand import summary

    monkeypatch.chdir(project)
    session = "sess-stop"
    core = open_core(project)
    _found_short(core, transcripts)
    cards = _own(project, session, "INT-009")

    ctx = HookContext("stop", {}, project, session, Deadline(30_000))
    parts = summary.stop_parts(ctx, open_core(project), {"turn_start": time.time() - 3600})
    assert '"Keep each card to one screen at most" (4 Oct)' in "\n".join(parts.cards)
    assert '"Keep each card to one screen at most" (4 Oct)' in "\n".join(stop.drawn_now(open_core(project), cards, {}))
