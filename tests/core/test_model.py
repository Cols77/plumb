"""K2: parsing records from Markdown with YAML frontmatter."""

from __future__ import annotations

import pytest

from plumb.model import RecordError, parse_record

pytestmark = pytest.mark.sr("SR-001")

KINDS = {
    "INT-001": "intent", "SR-001": "requirement", "DEC-001": "decision",
    "FEAT-001": "feature", "NC-0001": "nc",
}


@pytest.mark.parametrize("record_id,kind", sorted(KINDS.items()))
def test_parses_each_kind_from_frontmatter(record_id: str, kind: str) -> None:
    text = f"---\nid: {record_id}\ntitle: A title\nstatus_note: n\n---\nBody text\n"
    record = parse_record(text, ".plumb/x/file.md")
    assert record.id == record_id
    assert record.kind == kind
    assert record.title == "A title"
    assert record.fields == {"status_note": "n"}
    assert record.body == "Body text\n"
    assert record.path == ".plumb/x/file.md"
    assert record.hash.startswith("sha256:")


def test_identity_comes_from_frontmatter_not_filename() -> None:
    record = parse_record("---\nid: SR-007\ntitle: t\n---\n", ".plumb/requirements/SR-001.md")
    assert record.id == "SR-007"


@pytest.mark.parametrize("bad", ["SR-1", "SR-01", "NC-001", "XX-001", "sr-001", "", None])
def test_rejects_malformed_id(bad: object) -> None:
    text = f"---\nid: {bad if bad is not None else ''}\ntitle: t\n---\n"
    with pytest.raises(RecordError):
        parse_record(text, "p.md")


def test_rejects_missing_frontmatter_and_title() -> None:
    with pytest.raises(RecordError):
        parse_record("no frontmatter\n", "p.md")
    with pytest.raises(RecordError):
        parse_record("---\nid: SR-001\n---\n", "p.md")
    with pytest.raises(RecordError):
        parse_record("---\nid: SR-001\ntitle: [unclosed\n---\n", "p.md")


def test_requirement_examples_parsed_with_ids() -> None:
    text = """---
id: SR-003
title: Links pin both ends
statement: s
examples:
  - id: EX-1
    given: g
    when: w
    then: t
  - {id: AC-2, criterion: imported text}
links:
  - {kind: derives_from, to: INT-006, pin: {from: "sha256:a", to: "sha256:b"}}
  - {kind: verified_by, path: tests/test_x.py, example: EX-1}
---
"""
    record = parse_record(text, "p.md")
    assert [e.id for e in record.examples] == ["EX-1", "AC-2"]
    assert record.examples[0].given == "g" and record.examples[0].then == "t"
    assert record.examples[1].criterion == "imported text"
    assert "links" not in record.fields and "examples" in record.fields
    first, second = record.links
    assert first.id == "SR-003#0" and first.kind == "derives_from"
    assert first.target.record == "INT-006"
    assert first.pin is not None and first.pin.source == "sha256:a"
    assert first.pin.target == "sha256:b"
    assert second.target.path == "tests/test_x.py" and second.example == "EX-1"
    assert second.pin is None


def test_crlf_frontmatter_parses() -> None:
    record = parse_record("---\r\nid: SR-001\r\ntitle: t\r\n---\r\nbody\r\n", "p.md")
    assert record.id == "SR-001"
