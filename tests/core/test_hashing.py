"""K2: record hashes ignore formatting and change with meaning (spec 5.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.hashing import hash_path
from plumb.model import parse_record

pytestmark = pytest.mark.sr("SR-002")

BASE = """---
id: SR-001
title: Links pin both ends
statement: Both ends are pinned.
examples:
  - {id: EX-1, given: g, when: w, then: t}
---
Body line.
"""


def _hash(text: str) -> str:
    return parse_record(text, "p.md").hash


def test_record_hash_ignores_yaml_style_and_key_order() -> None:
    restyled = """---
title: 'Links pin both ends'
statement: >-
  Both ends are
  pinned.
id: "SR-001"
examples:
  - id: EX-1
    then: t
    when: w
    given: g
---
Body line.
"""
    assert _hash(restyled) == _hash(BASE)


def test_record_hash_ignores_links_field() -> None:
    linked = BASE.replace("---\nBody", "links:\n  - {kind: derives_from, to: INT-001}\n---\nBody")
    assert _hash(linked) == _hash(BASE)


def test_record_hash_ignores_crlf_trailing_space_and_derived_blocks() -> None:
    noisy = BASE.replace("Body line.\n", "Body line.   \n\n<!-- derived -->\nx\n"
                         "<!-- end derived -->\n\n").replace("\n", "\r\n")
    assert _hash(noisy) == _hash(BASE)


def test_record_hash_changes_on_statement_edit() -> None:
    assert _hash(BASE.replace("Both ends are pinned.", "One end is pinned.")) != _hash(BASE)
    assert _hash(BASE.replace("Body line.", "Other body.")) != _hash(BASE)
    assert _hash(BASE.replace("then: t", "then: u")) != _hash(BASE)


def test_file_end_hash_ignores_crlf(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x = 1\ny = 2\n")
    first = hash_path(tmp_path, "a.py")
    (tmp_path / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert hash_path(tmp_path, "a.py") == first
    (tmp_path / "a.py").write_bytes(b"x = 1\ny = 3\n")
    assert hash_path(tmp_path, "a.py") != first
    assert hash_path(tmp_path, "missing.py") is None
    assert hash_path(tmp_path, "../a.py") is None
    assert hash_path(tmp_path, ".") is None
