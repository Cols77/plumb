"""SR-118: the words a transcript search found reach the cards the owner presses: ``plumb mod
draw`` (the panel), the stop hook's read-back and the end-of-turn summary all show the span,
its date and session, "found in a transcript, not verified" and, for a record that misreads
the owner, the proposed rewording. A misreading's span too short to show is said to be too
short, like a supporting one. Fake models and a temp transcript directory only."""

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
    from plumb.understand import cardstore, read

    core = open_core(root)
    cards = [read.show_first_card(core.index()[rid], "words") for rid in ids]
    cardstore.save(root, session, [*cardstore.own_cards(root, session), *cards])
    return cards


def _drawn(monkeypatch, capsys, root: Path) -> dict[str, dict]:
    from mod.helpers import DIGEST, KEY, run_mod

    assert run_mod(monkeypatch, capsys, root, "hello", stdin={"key_digest": DIGEST})[0] == 0
    code, drawn, _ = run_mod(monkeypatch, capsys, root, "draw", stdin={"key": KEY})
    assert code == 0
    return {card["id"]: card for card in drawn["cards"]}


def test_mod_draw_carries_the_found_words_and_the_proposed_rewording(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    from mod.helpers import SESSION

    core = open_core(project)
    _found_short(core, transcripts)
    _misreads(core, transcripts)
    short, digest = _own(project, SESSION, "INT-009", "INT-020")
    drawn = _drawn(monkeypatch, capsys, project)

    (item,) = drawn[short.id]["content"]["owner_words"]["items"]
    assert item["id"] == "INT-009"
    found = item["found"]
    assert (found["status"], found["span"], found["session"]) == ("found", SPAN, "sess-1")
    assert found["at"].startswith("2026-10-04") and found["note"] == recover.NOT_VERIFIED
    assert item["found_lines"] == [f'found in a transcript of 2026-10-04 (session sess-1), '
                                   f'not verified: "{SPAN}"']

    (item,) = drawn[digest.id]["content"]["owner_words"]["items"]
    assert item["found"]["status"] == "misreads"
    assert item["found"]["proposed_wording"] == REWORDING
    lines = item["found_lines"]
    assert lines[0].startswith("found in a transcript of 2026-10-06 (session sess-2), "
                               "not verified:")
    assert "send me a digest every week" in lines[0]
    assert any("may misread you" in line for line in lines)
    assert f'proposed rewording: "{REWORDING}"' in lines
    # shown, never trusted: drawing the cards confirms nothing
    statuses = open_core(project).status()
    assert statuses["INT-009"].confirmation == statuses["INT-020"].confirmation == "proposed"


def test_the_stop_summary_and_read_back_show_the_found_words(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code import stop
    from plumb.hosts.claude_code.hookio import Deadline, HookContext
    from plumb.understand import summary

    monkeypatch.chdir(project)
    session = "sess-stop"
    core = open_core(project)
    _found_short(core, transcripts)
    _misreads(core, transcripts)
    cards = _own(project, session, "INT-009", "INT-020")

    ctx = HookContext("stop", {}, project, session, Deadline(30_000))
    parts = summary.stop_parts(ctx, open_core(project), {"turn_start": time.time() - 3600})
    text = "\n".join(parts.cards)
    assert f'found in a transcript of 2026-10-04 (session sess-1), not verified: "{SPAN}"' in text
    assert "found in a transcript of 2026-10-06 (session sess-2), not verified" in text
    assert f'proposed rewording: "{REWORDING}"' in text

    read_back = "\n".join(stop.drawn_now(open_core(project), cards, {}))
    assert f'not verified: "{SPAN}"' in read_back
    assert f'proposed rewording: "{REWORDING}"' in read_back


def test_a_misreading_span_under_four_words_is_too_short_to_show(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    from mod.helpers import SESSION

    core = open_core(project)
    _misreads(core, transcripts, span="a digest")
    core = open_core(project)
    finding = recover.finding_for(core, core.index()["INT-020"])
    assert (finding["status"], finding["by"], finding["span"]) == ("too_short", "opus", "")
    assert finding["proposed_wording"] == ""
    (card,) = _own(project, SESSION, "INT-020")
    (item,) = _drawn(monkeypatch, capsys, project)[card.id]["content"]["owner_words"]["items"]
    assert item["found_lines"] == [recover.TOO_SHORT]
    assert not any("proposed rewording" in line or "a digest" in line
                   for line in item["found_lines"])


def test_a_trial_card_shows_the_found_words(
        project: Path, transcripts: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """The owner kept the JEV judge with trial cards: a trial batch card for the records shows
    what the transcript search found for each, in the panel and the end-of-turn text."""
    from mod.helpers import SESSION
    from plumb.understand import cardstore, fullcard, trial

    core = open_core(project)
    _found_short(core, transcripts)
    _misreads(core, transcripts)
    core = open_core(project)
    index = core.index()
    batch = trial.batch_card([trial.Candidate(index[rid], 0.99, {}) for rid in
                              ("INT-009", "INT-020")], 0.5)
    single = trial.individual_card(trial.Candidate(index["INT-009"], 0.99, {}, "confirm"))
    cardstore.save(project, SESSION, [*cardstore.own_cards(project, SESSION), batch, single])

    drawn = _drawn(monkeypatch, capsys, project)
    items = {i["id"]: i for i in drawn[batch.id]["content"]["owner_words"]["items"]}
    assert items["INT-009"]["found_lines"] == [
        f'found in a transcript of 2026-10-04 (session sess-1), not verified: "{SPAN}"']
    assert f'proposed rewording: "{REWORDING}"' in items["INT-020"]["found_lines"]
    (item,) = drawn[single.id]["content"]["owner_words"]["items"]
    assert item["found_lines"] == items["INT-009"]["found_lines"]

    text = fullcard.render(fullcard.content(open_core(project), batch))
    assert f'not verified: "{SPAN}"' in text
    assert f'proposed rewording: "{REWORDING}"' in text
