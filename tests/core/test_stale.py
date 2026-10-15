"""SP8 lane STALE (SR-111): the link map, the stale links an edit causes, and the records
that derive from a reworded one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import stale
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-111")

SR5 = """---
id: SR-005
title: Relay checks the quote
statement: relay checks the quote.
examples:
- id: EX-1
  given: a quote
  when: relay runs
  then: it checks it
---
"""
INT16 = """---
id: INT-016
title: Add multiply
quote: add multiply
readback: Add multiply beside add
will:
- multiply returns a product
---
"""
SR32 = """---
id: SR-032
title: Multiply returns the product
statement: multiply(a, b) returns a * b
examples:
- id: EX-1
  given: 2 and 3
  when: multiply runs
  then: 6
---
"""
CODE = """def f(a, b):
    return a + b


def g(x):
    return x
"""


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR5)
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text(CODE, encoding="utf-8")
    (repo / "src" / "other.py").write_text("y = 1\n", encoding="utf-8")
    open_core(repo).add_link("SR-005", "implemented_by", Target(path="src/x.py", symbol="f"))
    stale.ensure_linkmap(open_core(repo))
    return repo


def test_ex1_function_edit_names_sr005_link(project: Path) -> None:
    assert stale.stale_after_edit(project, "src/x.py") == []
    (project / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    found = stale.stale_after_edit(project, "src/x.py")
    assert [(s.record, s.link, s.path) for s in found] == [("SR-005", "SR-005#0", "src/x.py")]
    assert stale.notice(found[0]) == (
        "plumb: SR-005's link to src/x.py is stale: the file changed; rerun its tests and "
        "repin, reword SR-005, or bring it to the owner as a card")


def test_reformat_only_symbol_edit_not_stale(project: Path) -> None:
    text = CODE.replace("a + b", "a + b   ").replace("return x", "return x  # other function")
    (project / "src" / "x.py").write_text(text.replace("\n\n\ndef g", "\n\n\n\ndef g"),
                                          encoding="utf-8")
    assert stale.stale_after_edit(project, "src/x.py") == []
    assert [e.link for e in stale.links_touching(project, "src/x.py")] == ["SR-005#0"]


def test_unrelated_file_nothing(project: Path) -> None:
    (project / "src" / "other.py").write_text("y = 2\n", encoding="utf-8")
    assert stale.links_touching(project, "src/other.py") == []
    assert stale.stale_after_edit(project, "src/other.py") == []


def test_missing_cache_silent(project: Path) -> None:
    (project / ".plumb" / "cache" / "linkmap.json").unlink()
    (project / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    assert stale.links_touching(project, "src/x.py") == []
    assert stale.stale_after_edit(project, "src/x.py") == []


def test_linkmap_rebuilt_on_index_change(project: Path, write_record) -> None:
    path = project / ".plumb" / "cache" / "linkmap.json"
    before = path.read_bytes()
    core = open_core(project)
    assert stale.ensure_linkmap(core) is False          # same index: no rewrite
    assert path.read_bytes() == before
    core.add_link("SR-005", "implemented_by", Target(path="src/other.py"))
    assert stale.ensure_linkmap(open_core(project)) is True
    assert json.loads(path.read_text(encoding="utf-8"))["ends"].keys() >= {"src/other.py"}
    assert [e.link for e in stale.links_touching(project, "src/other.py")] == ["SR-005#1"]


def _derived(repo: Path, write_record) -> None:
    write_record(repo, INT16)
    write_record(repo, SR32)
    open_core(repo).add_link("SR-032", "derives_from", Target(record="INT-016"))


def test_ex2_reword_names_derived_record(repo: Path, write_record) -> None:
    _derived(repo, write_record)
    assert stale.derived_lines(open_core(repo), ["INT-016"]) == []
    write_record(repo, INT16.replace("Add multiply beside add", "Add multiply and divide"))
    assert stale.derived_lines(open_core(repo), ["INT-016"]) == [
        "SR-032 derives from INT-016, which was reworded: check that it still agrees"]


def test_ex2_through_capture(repo: Path, write_record, tmp_path: Path, capsys) -> None:
    from plumb.cli import main

    _derived(repo, write_record)
    doc = tmp_path / "c.json"
    doc.write_text(json.dumps({"updates": [{"id": "INT-016",
                                            "readback": "Add multiply and divide"}]}),
                   encoding="utf-8")
    assert main(["capture", "--file", str(doc), "--root", str(repo)]) == 0
    assert ("SR-032 derives from INT-016, which was reworded: check that it still agrees"
            in capsys.readouterr().out)


def test_direct_record_edit_notice(repo: Path, write_record) -> None:
    _derived(repo, write_record)
    stale.ensure_linkmap(open_core(repo))
    assert stale.record_for_path(repo, ".plumb/intents/INT-016.md") == "INT-016"
    write_record(repo, INT16.replace("Add multiply beside add", "Add multiply and divide"))
    assert stale.derived_lines(open_core(repo), ["INT-016"])


def test_a_retired_record_raises_no_stale_notice(project: Path, write_record) -> None:
    """SR-164: once SR-032 supersedes SR-005, an edit to SR-005's file is not reported."""
    write_record(project, SR32)
    open_core(project).add_link("SR-032", "supersedes", Target(record="SR-005"))
    stale.ensure_linkmap(open_core(project))
    (project / "src" / "x.py").write_text(CODE.replace("a + b", "a - b"), encoding="utf-8")
    assert stale.links_touching(project, "src/x.py") == []
    assert stale.stale_after_edit(project, "src/x.py") == []
