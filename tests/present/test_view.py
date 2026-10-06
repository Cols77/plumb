"""PS1: plumb view writes a generated Obsidian vault and a Canvas intent map that never
approves (R9 DEEP REVIEW, sp5 7, SR-066)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from present_helpers import FEAT1, INT1, SR1, SR2, write_all

from plumb import cli
from plumb.api import open_core
from plumb.contracts import Target
from plumb.view import GENERATED

pytestmark = pytest.mark.sr("SR-066")


@pytest.fixture
def records(repo: Path, write_record) -> Path:
    write_all(repo, write_record, SR1, SR2, INT1, FEAT1)
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "src" / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                                  "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_add():\n    pass\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/app/calc.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_calc.py"), "EX-1")
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo


def _snapshot(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())}


def _view(repo: Path, capsys) -> Path:
    assert cli.main(["view", "--root", str(repo)]) == 0
    capsys.readouterr()
    return repo / ".plumb" / "view"


def test_idempotent_bytes(records: Path, capsys) -> None:
    """EX-1: plumb view twice gives byte-identical output; a removed record's note goes."""
    out = _view(records, capsys)
    first = _snapshot(out)
    assert {"SR-001.md", "SR-001.EX-1.md", "INT-001.md", "FEAT-001.md", "index.md",
            "by-feature.md", "awaiting-you.md", "drift.md", "intent-map.canvas",
            "test--tests__test_calc.py.md", "code--src__app__calc.py.md"} <= set(first)
    assert all(GENERATED in text.decode("utf-8")[:400] for text in first.values())
    assert _snapshot(_view(records, capsys)) == first
    (records / ".plumb" / "requirements" / "SR-002.md").unlink()
    assert "SR-002.md" not in _snapshot(_view(records, capsys))


def test_notes_carry_state_badges_and_wikilinks(records: Path, capsys) -> None:
    out = _view(records, capsys)
    note = (out / "SR-001.md").read_text("utf-8")
    assert 'state: "proposed"' in note and "#awaits-you" in note
    assert "[[SR-001.EX-1]] given a = 1 and b = 2" in note
    assert "[[test--tests__test_calc.py|tests/test_calc.py]]" in note
    assert "[[code--src__app__calc.py|src/app/calc.py]]" in note
    assert "`plumb approve SR-001`" in note
    assert "[[SR-001]]" in (out / "test--tests__test_calc.py.md").read_text("utf-8")
    assert "derives_from [[INT-001]]" in (out / "SR-002.md").read_text("utf-8")
    awaiting = (out / "awaiting-you.md").read_text("utf-8")
    assert "plumb triage --approve low-risk" in awaiting and "plumb approve SR-002" in awaiting


def test_note_edit_changes_no_state(records: Path, capsys) -> None:
    """EX-2: editing a note to say confirmed approves nothing."""
    out = _view(records, capsys)
    note = out / "SR-001.md"
    note.write_text(note.read_text("utf-8").replace('"proposed"', '"confirmed"'), "utf-8")
    assert open_core(records).status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert not [e for e in open_core(records).events() if e.kind == "approval"]
    assert '"proposed"' in (_view(records, capsys) / "SR-001.md").read_text("utf-8")


def test_canvas_valid(records: Path, capsys) -> None:
    """EX-3: valid JSON Canvas, unique node ids, an edge for each derives_from link."""
    data = json.loads((_view(records, capsys) / "intent-map.canvas").read_text("utf-8"))
    ids = [n["id"] for n in data["nodes"]]
    assert len(ids) == len(set(ids))
    for node in data["nodes"]:
        assert {"id", "type", "x", "y", "width", "height"} <= set(node)
        if node["type"] == "file":
            assert (records / ".plumb" / "view" / node["file"]).is_file()
    for edge in data["edges"]:
        assert edge["fromNode"] in ids and edge["toNode"] in ids
    assert any(e["fromNode"] == "SR-002" and e["toNode"] == "INT-001"
               and e["label"] == "derives_from" for e in data["edges"])
    assert len({e["id"] for e in data["edges"]}) == len(data["edges"])
