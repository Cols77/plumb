"""K2: the record store: index, next ID, writing and duplicates."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.paths import IasoPaths
from iaso.store import Store

pytestmark = pytest.mark.sr("SR-230")


def test_new_id_per_kind_and_nc_four_digits(repo: Path, write_record) -> None:
    store = Store(IasoPaths(repo))
    assert store.next_id("requirement") == "SR-001"
    assert store.next_id("nc") == "NC-0001"
    write_record(repo, "---\nid: SR-009\ntitle: t\n---\n")
    write_record(repo, "---\nid: NC-0041\ntitle: t\n---\n")
    store = Store(IasoPaths(repo))
    assert store.next_id("requirement") == "SR-010"
    assert store.next_id("nc") == "NC-0042"
    assert store.next_id("intent") == "INT-001"


def test_write_record_round_trips(repo: Path) -> None:
    store = Store(IasoPaths(repo))
    record = store.write_record(
        "requirement",
        {"title": "Links pin both ends", "statement": "Both ends are pinned.",
         "feature": "FEAT-001",
         "examples": [{"id": "EX-1", "given": "g", "when": "w", "then": "t"}]},
        "Some body.\n",
    )
    assert record.id == "SR-001"
    path = repo / record.path
    assert path == repo / ".iaso" / "requirements" / "SR-001.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\nid: SR-001\ntitle: Links pin both ends\n")
    assert text.index("feature:") < text.index("statement:") < text.index("examples:")
    reloaded = Store(IasoPaths(repo)).index()["SR-001"]
    assert reloaded.hash == record.hash
    assert reloaded.examples[0].then == "t"
    assert reloaded.body == "Some body.\n"


def test_duplicate_ids_reported(repo: Path, write_record) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: a\n---\n")
    write_record(repo, "---\nid: SR-001\ntitle: b\n---\n", name="SR-001-copy.md")
    write_record(repo, "---\nid: SR-002\ntitle: [bad\n---\n")
    store = Store(IasoPaths(repo))
    index = store.index()
    assert "SR-001" in index
    problems = " | ".join(store.problems())
    assert "duplicate id SR-001" in problems
    assert "SR-002.md" in problems


def test_update_links_keeps_body_and_hash(repo: Path, write_record) -> None:
    write_record(repo, "---\nid: SR-001\ntitle: t\nstatement: s\n---\nexact  body\r\n")
    store = Store(IasoPaths(repo))
    before = store.index()["SR-001"]
    store.set_links("SR-001", [{"kind": "derives_from", "to": "INT-001"}])
    after = Store(IasoPaths(repo)).index()["SR-001"]
    assert after.hash == before.hash
    assert after.links[0].target.record == "INT-001"
    raw = (repo / ".iaso" / "requirements" / "SR-001.md").read_bytes()
    assert raw.endswith(b"---\nexact  body\r\n")


SR_TEXT = ("---\nid: SR-001\ntitle: Cached\nstatement: s\nexamples:\n- id: EX-1\n  given: g\n"
           "  when: w\n  then: t\nlinks:\n- kind: implemented_by\n  path: src/a.py\n---\nBody\n")


def test_index_cache_skips_yaml_and_keeps_hashes(repo: Path, write_record,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """A warm index reads the parsed frontmatter from .iaso/cache/index.json, keyed by
    each file's content digest: same records, same hashes, no YAML parse (spec 10)."""
    import iaso.model
    import iaso.store

    write_record(repo, SR_TEXT)
    write_record(repo, "---\nid: DEC-001\ntitle: D\nmatters: true\nalternatives: [b]\n---\n")
    cold = Store(IasoPaths(repo)).index()
    assert (repo / ".iaso" / "cache" / "index.json").is_file()

    def no_yaml(text):
        raise AssertionError("YAML parsed on a warm index")

    monkeypatch.setattr(iaso.model, "load_yaml", no_yaml)
    monkeypatch.setattr(iaso.store, "load_yaml", no_yaml)
    warm = Store(IasoPaths(repo)).index()
    assert warm == cold


def test_index_cache_reparses_a_changed_file_of_the_same_size(repo: Path,
                                                              write_record) -> None:
    write_record(repo, SR_TEXT)
    Store(IasoPaths(repo)).index()
    write_record(repo, SR_TEXT.replace("statement: s", "statement: x"))
    record = Store(IasoPaths(repo)).index()["SR-001"]
    assert record.fields["statement"] == "x"


def test_index_cache_never_stores_values_json_cannot_keep(repo: Path, write_record) -> None:
    write_record(repo, "---\nid: INT-001\ntitle: Dated\nquote: q\nwhen: 2026-10-05\n---\n")
    cold = Store(IasoPaths(repo)).index()["INT-001"]
    warm = Store(IasoPaths(repo)).index()["INT-001"]
    assert warm == cold and warm.hash == cold.hash


def test_index_cache_keys_on_size_and_mtime_before_the_digest(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-014: a warm index trusts a file whose (size, mtime) matches the cache: it reads no
    record file, hashes no text and does not revalidate the cached JSON."""
    import os
    import time

    import iaso.store

    for i in range(1, 4):
        path = write_record(repo, SR_TEXT.replace("SR-001", f"SR-00{i}"))
        old = time.time() - 60  # outside the racy window
        os.utime(path, (old, old))
    cold = Store(IasoPaths(repo)).index()
    Store(IasoPaths(repo)).index()  # the first warm load stamps what it re-read

    def forbidden(*args, **kwargs):
        raise AssertionError("record file or JSON revalidated on a stamp match")

    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(iaso.store, "_json_safe", forbidden)
    monkeypatch.setattr(iaso.store.hashlib, "sha256", forbidden)
    warm = Store(IasoPaths(repo)).index()
    assert warm == cold


def test_index_cache_rereads_a_file_modified_just_now(repo: Path, write_record) -> None:
    """A rewrite of the same size within the clock's resolution is still seen."""
    write_record(repo, SR_TEXT)
    Store(IasoPaths(repo)).index()
    Store(IasoPaths(repo)).index()
    write_record(repo, SR_TEXT.replace("statement: s", "statement: y"))
    assert Store(IasoPaths(repo)).index()["SR-001"].fields["statement"] == "y"
