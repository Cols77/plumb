"""K4: hash-pinned links and staleness (spec 5.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb import links
from plumb.api import open_core
from plumb.contracts import Pin, Target

pytestmark = pytest.mark.sr("SR-003")

INT = """---
id: INT-001
title: Grounded
quote: "make vibe coding grounded"
---
"""
SR = """---
id: SR-001
title: Links pin both ends
statement: Both ends are pinned.
examples:
  - {id: EX-1, given: g, when: w, then: t}
---
"""


@pytest.fixture
def setup(repo: Path, write_record):
    write_record(repo, INT)
    write_record(repo, SR)
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_bytes(b"x = 1\n")
    return repo


def _state(core, link_id: str):
    return {s.link.id: s for s in core.link_states()}[link_id]


def test_add_link_pins_both_ends(setup: Path) -> None:
    core = open_core(setup)
    link = core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    index = core.index()
    assert link.id == "SR-001#0"
    assert link.pin == Pin(index["SR-001"].hash, index["INT-001"].hash)
    reread = open_core(setup).index()["SR-001"].links[0]
    assert reread.pin == link.pin and reread.target.record == "INT-001"
    assert _state(open_core(setup), "SR-001#0").state == "current"


def test_pin_drift(setup: Path) -> None:
    core = open_core(setup)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    (setup / "src" / "mod.py").write_bytes(b"x = 2\n")
    path = setup / ".plumb" / "intents" / "INT-001.md"
    path.write_text(INT.replace("grounded\"", "grounded on records\""), encoding="utf-8")
    core = open_core(setup)
    for link_id in ("SR-001#0", "SR-001#1"):
        state = _state(core, link_id)
        assert state.state == "stale" and state.moved == "target"
        assert state.current is not None and state.current != state.link.pin


def test_crlf_is_not_drift(setup: Path) -> None:
    core = open_core(setup)
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    (setup / "src" / "mod.py").write_bytes(b"x = 1\r\n")
    assert _state(open_core(setup), "SR-001#0").state == "current"


def test_source_edit_marks_source_moved(setup: Path) -> None:
    core = open_core(setup)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    path = setup / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Both ends", "Each end"),
                    encoding="utf-8")
    (setup / ".plumb" / "intents" / "INT-001.md").write_text(
        INT.replace("Grounded", "Grounded work"), encoding="utf-8")
    state = _state(open_core(setup), "SR-001#0")
    assert state.state == "stale" and state.moved == "both"


def test_dangling_record_and_path(setup: Path, write_record) -> None:
    write_record(setup, SR.replace("---\nid: SR-001", "---\nid: SR-002").replace(
        "examples:", "links:\n  - {kind: derives_from, to: INT-009}\n"
        "  - {kind: implemented_by, path: src/gone.py}\nexamples:"))
    core = open_core(setup)
    assert _state(core, "SR-002#0").state == "dangling"
    assert _state(core, "SR-002#1").state == "dangling"


def test_unpinned_link_warns(setup: Path, write_record) -> None:
    write_record(setup, SR.replace("---\nid: SR-001", "---\nid: SR-002").replace(
        "examples:", "links:\n  - {kind: derives_from, to: INT-001}\nexamples:"))
    state = _state(open_core(setup), "SR-002#0")
    assert state.state == "unpinned" and state.current is not None


def test_link_kind_allowed_matrix() -> None:
    allowed = links.kind_allowed
    assert allowed("derives_from", "requirement", "intent")
    assert allowed("derives_from", "decision", "intent")
    assert allowed("derives_from", "feature", "intent")
    assert not allowed("derives_from", "requirement", "requirement")
    assert allowed("decides", "decision", "requirement")
    assert allowed("decides", "decision", "intent")
    assert not allowed("decides", "requirement", "intent")
    assert allowed("upstream", "requirement", "requirement")
    assert allowed("relates_to", "requirement", "requirement")
    assert allowed("implemented_by", "requirement", "code")
    assert not allowed("implemented_by", "requirement", "test")
    assert allowed("verified_by", "requirement", "test")
    assert allowed("verified_by", "requirement", "code")
    assert allowed("corrects", "nc", "requirement")
    assert allowed("corrects", "nc", "code")
    assert allowed("supersedes", "decision", "decision")
    assert not allowed("supersedes", "decision", "requirement")
    assert not allowed("bogus", "requirement", "intent")


def test_add_link_rejects_bad_kind_and_missing_end(setup: Path) -> None:
    core = open_core(setup)
    with pytest.raises(links.LinkError):
        core.add_link("SR-001", "derives_from", Target(record="SR-001"))
    with pytest.raises(links.LinkError):
        core.add_link("SR-001", "implemented_by", Target(path="src/missing.py"))
    with pytest.raises(links.LinkError):
        core.add_link("SR-404", "derives_from", Target(record="INT-001"))
    with pytest.raises(links.LinkError):
        core.add_link("SR-001", "verified_by", Target(path="src/mod.py"), example="EX-7")
    with pytest.raises(links.LinkUsageError):
        links.parse_cli_target("tests/test_x.py::test_y")
    with pytest.raises(links.LinkUsageError):
        links.parse_cli_target("/abs/path.py")
    assert links.parse_cli_target("INT-001") == Target(record="INT-001")
    assert links.parse_cli_target("src\\mod.py") == Target(path="src/mod.py")


def test_repin_refreshes_pins_and_logs_event(setup: Path) -> None:
    core = open_core(setup)
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    old_pin = core.index()["SR-001"].links[0].pin
    (setup / "src" / "mod.py").write_bytes(b"x = 3\n")
    core = open_core(setup)
    changed = links.repin(core, selector="SR-001")
    assert [c["link"] for c in changed] == ["SR-001#0"]
    core = open_core(setup)
    assert _state(core, "SR-001#0").state == "current"
    events = list(core.log_read("events", kinds=["repin"]))
    assert len(events) == 1
    entry = events[0].payload["links"][0]
    assert entry["old"] == {"from": old_pin.source, "to": old_pin.target}
    assert entry["new"]["to"] == core.hash_target(Target(path="src/mod.py"))
    assert links.repin(core, all_stale=True) == []


def test_repin_pins_unpinned_and_link_id_selector(setup: Path, write_record) -> None:
    write_record(setup, SR.replace("---\nid: SR-001", "---\nid: SR-002").replace(
        "examples:", "links:\n  - {kind: derives_from, to: INT-001}\nexamples:"))
    core = open_core(setup)
    assert [c["link"] for c in links.repin(core, selector="SR-002#0")] == ["SR-002#0"]
    assert _state(open_core(setup), "SR-002#0").state == "current"
    with pytest.raises(links.LinkError):
        links.repin(open_core(setup), selector="SR-002#5")


def test_repin_does_not_confirm(setup: Path) -> None:
    core = open_core(setup)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    (setup / ".plumb" / "intents" / "INT-001.md").write_text(INT.replace("Grounded", "G2"),
                                                             encoding="utf-8")
    links.repin(open_core(setup), all_stale=True)
    core = open_core(setup)
    assert core.status(["SR-001"])["SR-001"].confirmation == "proposed"
    assert list(core.log_read("events", kinds=["approval"])) == []


def test_records_for_paths(setup: Path) -> None:
    core = open_core(setup)
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    mapping = open_core(setup).records_for_paths(
        ["src/mod.py", ".plumb/requirements/SR-001.md", "other.py"])
    assert mapping["src/mod.py"] == ("SR-001",)
    assert mapping[".plumb/requirements/SR-001.md"] == ("SR-001",)
    assert mapping["other.py"] == ()
