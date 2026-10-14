"""SR-151: merge and early conflict cards reach the owner through fullcard, with no ids."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mergedriver.mdhelpers import OURS_STATEMENT, THEIRS_STATEMENT, conflicted
from plumb import cli
from plumb.api import open_core
from plumb.awareness.early import EarlyConflict
from plumb.mergedriver import open_conflicts
from plumb.mergedriver.conflicts import propose
from plumb.understand import cards, fullcard

pytestmark = pytest.mark.sr("SR-151")
IDS = re.compile(r"\b(IC|SR|INT|DEC)-\d+")


def _owner_text(core, card) -> str:
    return fullcard.render(fullcard.content(core, card))


def test_ex1_merge_card_by_title_both_versions_combined_no_ids(repo: Path) -> None:
    conflicted(repo)
    core = open_core(repo)
    (conflict,) = open_conflicts(core)
    conflict = propose(core, conflict.ic, {"statement": "both hold together"})
    text = _owner_text(core, cards.conflict_card(core.index(), conflict))
    assert "relay checks" in text
    assert OURS_STATEMENT in text and THEIRS_STATEMENT in text
    assert "both hold together" in text
    assert "1. " in text and "2. " in text and "Keeps" in text
    assert not IDS.search(text)


def test_ex2_agent_view_keeps_the_conflict_id(repo: Path, capsys) -> None:
    ic = conflicted(repo)
    assert cli.main(["conflicts", "--root", str(repo)]) == 0
    assert ic in capsys.readouterr().out


def test_ex3_early_card_same_shape_no_ids(repo: Path) -> None:
    conflicted(repo)
    core = open_core(repo)
    early = EarlyConflict(record="SR-005", title="relay checks", branch="feat-x",
                          claim="CL-1", theirs="checks run twice", ours="checks run once")
    text = _owner_text(core, cards.early_conflict_card(core.index(), early))
    assert "relay checks" in text and "checks run twice" in text and "checks run once" in text
    assert "1. " in text and "Keeps" in text or "written from both" in text
    assert not IDS.search(text)


def test_ex3_early_card_off_both_branches_labels_the_second_branch(repo: Path) -> None:
    conflicted(repo)
    core = open_core(repo)
    early = EarlyConflict(record="SR-005", title="relay checks", branch="feat-b",
                          claim="CL-1", theirs="checks run twice", ours="checks run once",
                          ours_label="feat-a")
    text = _owner_text(core, cards.early_conflict_card(core.index(), early))
    assert 'feat-a says "checks run once"' in text and "Keeps feat-a's version" in text
    assert "this work" not in text
