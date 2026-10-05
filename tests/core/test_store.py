"""K2: the record store: index, next ID, writing and duplicates."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.paths import PlumbPaths
from plumb.store import Store

pytestmark = pytest.mark.sr("SR-001")


def test_new_id_per_kind_and_nc_four_digits(repo: Path, write_record) -> None:
    store = Store(PlumbPaths(repo))
    assert store.next_id("requirement") == "SR-001"
    assert store.next_id("nc") == "NC-0001"
    write_record(repo, "---\nid: SR-009\ntitle: t\n---\n")
    write_record(repo, "---\nid: NC-0041\ntitle: t\n---\n")
    store = Store(PlumbPaths(repo))
    assert store.next_id("requirement") == "SR-010"
    assert store.next_id("nc") == "NC-0042"
    assert store.next_id("intent") == "INT-001"


def test_write_record_round_trips(repo: Path) -> None:
    store = Store(PlumbPaths(repo))
    record = store.write_record(
        "requirement",
        {"title": "Links pin both ends", "statement": "Both ends are pinned.",
         "feature": "FEAT-001",
         "examples": [{"id": "EX-1", "given": "g", "when": "w", "then": "t"}]},
        "Some body.\n",
    )
    assert record.id == "SR-001"
    path = repo / record.path
    assert path == repo / ".plumb" / "requirements" / "SR-001.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\nid: SR-001\ntitle: Links pin both ends\n")
    assert text.index("feature:") < text.index("statement:") < text.index("examples:")
    reloaded = Store(PlumbPaths(repo)).index()["SR-001"]
    assert reloaded.hash == record.hash
    assert reloaded.examples[0].then == "t"
    assert reloaded.body == "Some body.\n"


def test_duplicate_ids_reported(repo: Path, write_record) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: a\n---\n")
    write_record(repo, "---\nid: SR-001\ntitle: b\n---\n", name="SR-001-copy.md")
    write_record(repo, "---\nid: SR-002\ntitle: [bad\n---\n")
    store = Store(PlumbPaths(repo))
    index = store.index()
    assert "SR-001" in index
    problems = " | ".join(store.problems())
    assert "duplicate id SR-001" in problems
    assert "SR-002.md" in problems


def test_update_links_keeps_body_and_hash(repo: Path, write_record) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: t\nstatement: s\n---\nexact  body\r\n")
    store = Store(PlumbPaths(repo))
    before = store.index()["SR-001"]
    store.set_links("SR-001", [{"kind": "derives_from", "to": "INT-001"}])
    after = Store(PlumbPaths(repo)).index()["SR-001"]
    assert after.hash == before.hash
    assert after.links[0].target.record == "INT-001"
    raw = (repo / ".plumb" / "requirements" / "SR-001.md").read_bytes()
    assert raw.endswith(b"---\nexact  body\r\n")
