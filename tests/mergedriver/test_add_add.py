"""D2: add/add and the text fallback (sp6 7.5, 7.6)."""

from __future__ import annotations

import pytest

from mergedriver.mdhelpers import Counter, record
from plumb.mergedriver import merge_texts

LABELS = ("main", "feat-x")


@pytest.mark.sr("SR-075")
def test_same_id_different_content_exit_1_ours_kept() -> None:
    ours = record("SR-070", "one thing", statement="a")
    theirs = record("SR-070", "another thing", statement="b")
    result = merge_texts("", ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 1 and result.text == ours
    assert "created on both sides" in result.notes[0] and "/plumb merge-fix" in result.notes[0]


@pytest.mark.sr("SR-075")
def test_equal_content_exit_0() -> None:
    ours = record("SR-070", "one thing", statement="a")
    theirs = "---\ntitle: one thing\nid: SR-070\nstatement: a\n---\n"
    result = merge_texts("", ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 0 and result.conflict is None


@pytest.mark.sr("SR-075")
def test_unparsable_side_falls_back_to_text_merge() -> None:
    base = record(statement="a")
    ours = record(statement="b")
    theirs = "---\nid: SR-005\ntitle: [unclosed\n---\n"
    result = merge_texts(base, ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 1
    assert "<<<<<<< main" in result.text and ">>>>>>> feat-x" in result.text
    assert "keep mine" in result.notes[0] and "SR-005" in result.notes[0]


@pytest.mark.sr("SR-075")
def test_unparsable_side_clean_text_merge_exits_0() -> None:
    base = "not a record\nline\n"
    ours = "not a record\nline\nours\n"
    theirs = "theirs\nnot a record\nline\n"
    result = merge_texts(base, ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 0 and result.text == "theirs\nnot a record\nline\nours\n"
