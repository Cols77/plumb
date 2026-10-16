"""SR-150 EX-2: a merge conflict card's side is answered by pressing it, as the owner's own
choice (the agent never chooses for them)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mergedriver.mdhelpers import OURS_STATEMENT, conflicted, events, parse
from mod.helpers import DIGEST, KEY, SESSION, run_mod

from plumb.api import open_core
from plumb.mergedriver import open_conflicts
from plumb.understand import cards, cardstore, files, fullcard, summary


@pytest.mark.sr("SR-211")
def test_pressing_keep_mains_version_chooses_it(repo: Path, monkeypatch, capsys) -> None:
    conflicted(repo)
    core = open_core(repo)
    card = cards.conflict_card(core.index(), open_conflicts(core)[0])
    files.write_json_atomic(files.session_dir(repo, SESSION) / summary.DRAWN, [
        {"card": cardstore.card_to_json(card), "content": fullcard.content(core, card),
         "turn_built": True}])
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    _, drawn, _ = run_mod(monkeypatch, capsys, repo, "draw", stdin={"key": KEY})
    (shown,) = [c for c in drawn["cards"] if c["id"] == card.id]
    offer = shown["offers"][0]
    (button,) = [b for b in offer["buttons"] if b["label"] == cards.KEEP_THIS]
    code, result, _ = run_mod(monkeypatch, capsys, repo, "press", "--offer", offer["offer_id"],
                              "--choice", str(button["index"]), stdin={"key": KEY})
    assert code == 0 and result["status"] == "closed"
    record = parse((repo / ".plumb/requirements/SR-005.md").read_text(encoding="utf-8"))[0]
    assert record["statement"] == OURS_STATEMENT and "conflict" not in record
    (entry,) = events(repo, "conflict-resolution")
    assert (entry["take"], entry["by"]) == ("ours", "owner")


@pytest.mark.sr("SR-211")
def test_press_after_the_combined_version_changed_writes_nothing(repo: Path, monkeypatch,
                                                                 capsys) -> None:
    from plumb.mergedriver.conflicts import propose

    conflicted(repo)
    core = open_core(repo)
    card = cards.conflict_card(core.index(), open_conflicts(core)[0])
    files.write_json_atomic(files.session_dir(repo, SESSION) / summary.DRAWN, [
        {"card": cardstore.card_to_json(card), "content": fullcard.content(core, card),
         "turn_built": True}])
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    _, drawn, _ = run_mod(monkeypatch, capsys, repo, "draw", stdin={"key": KEY})
    offer = next(c for c in drawn["cards"] if c["id"] == card.id)["offers"][0]
    button = next(b for b in offer["buttons"] if b["label"] == cards.KEEP_THIS)
    propose(open_core(repo), open_conflicts(core)[0].ic, {"statement": "NEVER SHOWN combined"})
    code, _, _ = run_mod(monkeypatch, capsys, repo, "press", "--offer", offer["offer_id"],
                         "--choice", str(button["index"]), stdin={"key": KEY})
    assert code == 1 and not events(repo, "conflict-resolution")
