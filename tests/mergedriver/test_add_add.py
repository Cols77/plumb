"""D2: add/add and the text fallback (sp6 7.5, 7.6)."""

from __future__ import annotations

import pytest

from mergedriver.mdhelpers import Counter, record
from plumb.mergedriver import merge_texts

LABELS = ("main", "feat-x")


@pytest.mark.sr("SR-256")
def test_same_id_different_content_exit_1_ours_kept() -> None:
    ours = record("SR-070", "one thing", statement="a")
    theirs = record("SR-070", "another thing", statement="b")
    result = merge_texts("", ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 1 and result.text == ours
    assert "created on both sides" in result.notes[0] and "/plumb merge-fix" in result.notes[0]


@pytest.mark.sr("SR-256")
def test_equal_content_exit_0() -> None:
    ours = record("SR-070", "one thing", statement="a")
    theirs = "---\ntitle: one thing\nid: SR-070\nstatement: a\n---\n"
    result = merge_texts("", ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 0 and result.conflict is None


@pytest.mark.sr("SR-256")
def test_unparsable_side_falls_back_to_text_merge() -> None:
    base = record(statement="a")
    ours = record(statement="b")
    theirs = "---\nid: SR-005\ntitle: [unclosed\n---\n"
    result = merge_texts(base, ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 1
    assert "<<<<<<< main" in result.text and ">>>>>>> feat-x" in result.text
    assert "keep mine" in result.notes[0] and "SR-005" in result.notes[0]


@pytest.mark.sr("SR-256")
def test_unparsable_side_clean_text_merge_exits_0() -> None:
    base = "not a record\nline\n"
    ours = "not a record\nline\nours\n"
    theirs = "theirs\nnot a record\nline\n"
    result = merge_texts(base, ours, theirs, labels=LABELS, reserve_ic=Counter())
    assert result.exit == 0 and result.text == "theirs\nnot a record\nline\nours\n"


@pytest.mark.sr("SR-256")
def test_validate_names_a_text_merged_record(repo) -> None:
    """sp6 7.6: a record file left with conflict markers is named in the owner's terms."""
    from mergedriver.mdhelpers import plumb, write_record
    from plumb.present.owner_text import bare_cli_verbs

    path = write_record(repo, record(statement="a"))
    text = merge_texts(record(statement="a"), record(statement="b"),
                       "---\nid: SR-005\ntitle: [x\n---\n", labels=LABELS,
                       reserve_ic=Counter()).text
    path.write_text(text, encoding="utf-8")
    out = plumb(repo, "validate")
    assert out.returncode == 1
    line = next(x for x in out.stdout.splitlines() if "both versions of a text merge" in x)
    assert 'say "keep mine" or "keep theirs"' in line and "SR-005" in line
    assert bare_cli_verbs(line) == []
