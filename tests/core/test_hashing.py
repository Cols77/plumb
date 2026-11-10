"""K2: record hashes ignore formatting and change with meaning (spec 5.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.hashing import hash_path
from iaso.model import parse_record

pytestmark = pytest.mark.sr("SR-230")

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


# --------------------------------------------------------------------------- I3: AST link ends

MODULE = '''"""Module."""

import functools


@functools.cache
def fn(a):
    return a + 1


class Box:
    size = 3

    def open(self):
        return "open"


def other():
    return 0
'''

TESTS = '''import pytest


@pytest.mark.parametrize("n", [1, 2])
def test_add(n):
    assert n


class TestBox:
    def test_open(self):
        assert True


def test_other():
    assert True
'''


@pytest.fixture
def code(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text(MODULE, encoding="utf-8", newline="\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(TESTS, encoding="utf-8", newline="\n")
    return tmp_path


def _rewrite(path: Path, old: str, new: str) -> None:
    path.write_bytes(path.read_bytes().replace(old.encode(), new.encode()))


@pytest.mark.sr("SR-238")
def test_symbol_end_ignores_edits_elsewhere(code: Path) -> None:
    from iaso.contracts import Target
    from iaso.hashing import hash_target

    end = Target(path="src/x.py", symbol="pkg.x:fn")
    method = Target(path="src/x.py", symbol="Box.open")
    first, first_method = hash_target(code, {}, end), hash_target(code, {}, method)
    assert first and first_method and first != first_method
    # the module form and the bare qualified name name the same definition
    assert hash_target(code, {}, Target(path="src/x.py", symbol="fn")) == first
    _rewrite(code / "src" / "x.py", "return 0", "return 1")         # elsewhere
    _rewrite(code / "src" / "x.py", '"""Module."""', '"""Edited."""')
    (code / "src" / "x.py").write_bytes((code / "src" / "x.py").read_bytes()
                                         .replace(b"\n", b"\r\n"))  # CRLF only
    assert hash_target(code, {}, end) == first
    assert hash_target(code, {}, method) == first_method
    _rewrite(code / "src" / "x.py", "return a + 1", "return a + 2")  # the definition
    assert hash_target(code, {}, end) != first
    _rewrite(code / "src" / "x.py", "@functools.cache\n", "")        # its decorator counts
    assert hash_target(code, {}, end) not in (None, first)
    assert hash_target(code, {}, method) == first_method


@pytest.mark.sr("SR-238")
def test_test_node_drops_parametrize_ids(code: Path) -> None:
    from iaso.contracts import Target
    from iaso.hashing import hash_target

    plain = hash_target(code, {}, Target(test="tests/test_x.py::test_add"))
    assert plain is not None
    assert hash_target(code, {}, Target(test="tests/test_x.py::test_add[1]")) == plain
    assert hash_target(code, {}, Target(test="tests/test_x.py::test_add[2]")) == plain
    nested = hash_target(code, {}, Target(test="tests/test_x.py::TestBox::test_open"))
    assert nested is not None and nested != plain
    _rewrite(code / "tests" / "test_x.py", "assert True\n\n\ndef test_other",
             "assert False\n\n\ndef test_other")                    # test_open changes
    assert hash_target(code, {}, Target(test="tests/test_x.py::test_add")) == plain
    assert hash_target(code, {}, Target(test="tests/test_x.py::TestBox::test_open")) != nested


@pytest.mark.sr("SR-238")
def test_missing_symbol_dangles(code: Path) -> None:
    from iaso.contracts import Target
    from iaso.hashing import hash_target

    assert hash_target(code, {}, Target(path="src/x.py", symbol="gone")) is None
    assert hash_target(code, {}, Target(path="src/x.py", symbol="Box.shut")) is None
    assert hash_target(code, {}, Target(test="tests/test_x.py::test_gone")) is None
    assert hash_target(code, {}, Target(test="tests/missing.py::test_add")) is None
    (code / "src" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    assert hash_target(code, {}, Target(path="src/bad.py", symbol="broken")) is None
    assert hash_target(code, {}, Target(path="../x.py", symbol="fn")) is None
