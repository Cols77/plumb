"""K4: hash-pinned links and staleness (spec 5.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb import approvals, links
from plumb.api import open_core
from plumb.contracts import Pin, Target

pytestmark = pytest.mark.sr("SR-231")

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
        links.parse_cli_target("src/mod.py::")
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


@pytest.mark.sr("SR-238")
def test_symbol_and_test_node_ends_from_the_cli_form(setup: Path) -> None:
    (setup / "src" / "mod.py").write_text("def fn():\n    return 1\n\n\ndef g():\n    pass\n",
                                          encoding="utf-8")
    (setup / "tests").mkdir()
    (setup / "tests" / "test_mod.py").write_text(
        "import pytest\n\n\n@pytest.mark.parametrize('n', [1])\ndef test_fn(n):\n"
        "    assert n\n", encoding="utf-8")
    assert links.parse_cli_target("src\\mod.py::fn") == Target(path="src/mod.py", symbol="fn")
    core = open_core(setup)
    impl = core.add_link("SR-001", "implemented_by", links.parse_cli_target("src/mod.py::fn"))
    assert impl.target == Target(path="src/mod.py", symbol="fn")
    # a verified_by end named path::name is a test node; parametrize ids are dropped
    ver = core.add_link("SR-001", "verified_by",
                        links.parse_cli_target("tests/test_mod.py::test_fn[1]"), "EX-1")
    assert ver.target == Target(test="tests/test_mod.py::test_fn")
    reread = open_core(setup).index()["SR-001"].links
    assert [link.target for link in reread] == [impl.target, ver.target]
    # an edit elsewhere in the file leaves the symbol end current
    path = setup / "src" / "mod.py"
    path.write_text(path.read_text(encoding="utf-8").replace("pass", "return 2"),
                    encoding="utf-8")
    assert {s.link.id: s.state for s in open_core(setup).link_states()} == {
        "SR-001#0": "current", "SR-001#1": "current"}
    # removing the symbol makes the link dangling
    path.write_text("def g():\n    pass\n", encoding="utf-8")
    assert _state(open_core(setup), "SR-001#0").state == "dangling"
    with pytest.raises(links.LinkError):
        open_core(setup).add_link("SR-001", "implemented_by",
                                  links.parse_cli_target("src/mod.py::fn"))


# --------------------------------------------------------------------------- unlink and relink

TWO = SR.replace("examples:\n", "examples:\n  - {id: EX-2, given: g2, when: w2, then: t2}\n")


@pytest.fixture
def edit(repo: Path, write_record) -> Path:
    write_record(repo, INT)
    write_record(repo, TWO)
    (repo / "tests").mkdir()
    for name in ("test_a.py", "test_b.py", "test_old.py"):
        (repo / "tests" / name).write_text("def test_x():\n    pass\n", encoding="utf-8")
    root = ["--root", str(repo)]
    from plumb import cli

    assert cli.main(["link", "SR-001", "derives_from", "INT-001", *root]) == 0
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_old.py", "--example", "EX-1",
                     *root]) == 0
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_a.py", "--example", "EX-1",
                     *root]) == 0
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_b.py", "--example", "EX-2",
                     *root]) == 0
    return repo


def _cli(repo: Path, *argv: str) -> int:
    from plumb import cli

    return cli.main([*argv, "--root", str(repo)])


def _record_text(repo: Path) -> str:
    return (repo / ".plumb" / "requirements" / "SR-001.md").read_text(encoding="utf-8")


def _ends(repo: Path) -> list[str | None]:
    return [link.target.record or link.target.path
            for link in open_core(repo).index()["SR-001"].links]


@pytest.mark.sr("SR-231")
def test_unlink_removes_a_dangling_link_renumbers_and_logs(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (edit / "tests" / "test_old.py").unlink()
    pin = open_core(edit).index()["SR-001"].links[1].pin
    capsys.readouterr()
    assert _cli(edit, "unlink", "SR-001#1", "--note", "the test moved") == 0
    out = capsys.readouterr().out
    assert _ends(edit) == ["INT-001", "tests/test_a.py", "tests/test_b.py"]
    assert "SR-001#2 is now SR-001#1" in out and "SR-001#3 is now SR-001#2" in out
    events = [e.payload for e in open_core(edit).log_read("events", kinds=["unlink"])]
    assert events == [{"link": "SR-001#1", "kind": "verified_by",
                       "target": "tests/test_old.py", "example": "EX-1",
                       "pin": {"from": pin.source, "to": pin.target},
                       "note": "the test moved",
                       "renumbered": [{"from": "SR-001#2", "to": "SR-001#1"},
                                      {"from": "SR-001#3", "to": "SR-001#2"}]}]


@pytest.mark.sr("SR-231")
def test_unlink_of_a_missing_link_exits_1_and_changes_nothing(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _record_text(edit)
    capsys.readouterr()
    assert _cli(edit, "unlink", "SR-001#40", "--note", "x") == 1
    assert "no link SR-001#40" in capsys.readouterr().err
    assert _record_text(edit) == before


@pytest.mark.sr("SR-231")
def test_unlink_without_a_note_is_a_usage_error(edit: Path) -> None:
    before = _record_text(edit)
    assert _cli(edit, "unlink", "SR-001#1") == 2
    assert _record_text(edit) == before
    assert list(open_core(edit).log_read("events", kinds=["unlink"])) == []


@pytest.mark.sr("SR-231")
def test_unlink_refuses_the_only_live_test_of_a_confirmed_example(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    approvals.approve(open_core(edit), ["SR-001"])
    before = _record_text(edit)
    capsys.readouterr()
    assert _cli(edit, "unlink", "SR-001#3", "--note", "x") == 1
    err = capsys.readouterr().err
    assert "EX-2" in err and "only test" in err and "plumb relink" in err
    assert _record_text(edit) == before
    # EX-1 keeps another live test, so one of its two may go
    assert _cli(edit, "unlink", "SR-001#1", "--note", "a duplicate test") == 0


@pytest.mark.sr("SR-231")
def test_unlink_removes_a_dangling_only_test_of_a_confirmed_example(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    approvals.approve(open_core(edit), ["SR-001"])
    (edit / "tests" / "test_b.py").unlink()
    capsys.readouterr()
    assert _cli(edit, "unlink", "SR-001#3", "--note", "the test is gone") == 0
    assert "EX-2 now has no test" in capsys.readouterr().out
    assert "tests/test_b.py" not in _ends(edit)


@pytest.mark.sr("SR-231")
def test_relink_points_a_dangling_link_at_the_new_target(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (edit / "tests" / "mod").mkdir()
    (edit / "tests" / "test_old.py").rename(edit / "tests" / "mod" / "test_old.py")
    old = open_core(edit).index()["SR-001"].links[1]
    assert _cli(edit, "relink", "SR-001#1", "tests/mod/test_old.py", "--note", "moved") == 0
    core = open_core(edit)
    link = core.index()["SR-001"].links[1]
    assert (link.kind, link.target, link.example) == (
        "verified_by", Target(path="tests/mod/test_old.py"), "EX-1")
    assert link.pin == Pin(core.index()["SR-001"].hash,
                           core.hash_target(Target(path="tests/mod/test_old.py")))
    assert _state(core, "SR-001#1").state == "current"
    events = [e.payload for e in core.log_read("events", kinds=["relink"])]
    assert events == [{"link": "SR-001#1", "note": "moved",
                       "old": {"target": "tests/test_old.py",
                               "pin": {"from": old.pin.source, "to": old.pin.target}},
                       "new": {"target": "tests/mod/test_old.py",
                               "pin": {"from": link.pin.source, "to": link.pin.target}}}]


@pytest.mark.sr("SR-231")
def test_relink_to_a_missing_target_exits_1_and_changes_nothing(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _record_text(edit)
    capsys.readouterr()
    assert _cli(edit, "relink", "SR-001#1", "tests/nowhere.py", "--note", "x") == 1
    assert "tests/nowhere.py" in capsys.readouterr().err
    assert _record_text(edit) == before


@pytest.mark.sr("SR-231")
def test_relink_refuses_to_copy_another_link(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _record_text(edit)
    capsys.readouterr()
    assert _cli(edit, "relink", "SR-001#1", "tests/test_a.py", "--note", "x") == 1
    err = capsys.readouterr().err
    assert "SR-001#2" in err and "plumb unlink" in err
    assert _record_text(edit) == before


@pytest.mark.sr("SR-231")
def test_relink_refuses_a_kind_that_cannot_reach_the_target(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _record_text(edit)
    capsys.readouterr()
    assert _cli(edit, "relink", "SR-001#0", "tests/test_a.py", "--note", "x") == 1
    assert "derives_from is not allowed from requirement to code" in capsys.readouterr().err
    assert _record_text(edit) == before


@pytest.mark.sr("SR-231")
def test_unlink_lets_a_retired_examples_test_go(
        edit: Path, capsys: pytest.CaptureFixture[str]) -> None:
    approvals.approve(open_core(edit), ["SR-001"])
    path = edit / ".plumb" / "requirements" / "SR-001.md"
    # EX-2 is retired (renumbered away); SR-001#3 still names it
    path.write_text(_record_text(edit).replace("id: EX-2", "id: EX-7"), encoding="utf-8")
    assert {e.id for e in open_core(edit).index()["SR-001"].examples} == {"EX-1", "EX-7"}
    capsys.readouterr()
    assert _cli(edit, "unlink", "SR-001#3", "--note", "EX-2 was retired") == 0
    assert "no test" not in capsys.readouterr().out


@pytest.mark.sr("SR-231")
def test_unlink_lets_a_superseded_records_only_test_go(
        edit: Path, write_record, capsys: pytest.CaptureFixture[str]) -> None:
    """DEC-065: every example of a superseded record is retired, so its tests go with it."""
    approvals.approve(open_core(edit), ["SR-001"])
    write_record(edit, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    assert _cli(edit, "link", "SR-002", "supersedes", "SR-001") == 0
    capsys.readouterr()
    assert _cli(edit, "unlink", "SR-001#3", "--note", "DEC-065") == 0
    assert "tests/test_b.py" not in _ends(edit)


def _superseded(setup: Path, write_record):
    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    core = open_core(setup)
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    old_pin = core.index()["SR-001"].links[0].pin
    (setup / "src" / "mod.py").write_bytes(b"x = 2\n")
    assert _state(open_core(setup), "SR-001#0").state == "stale"
    open_core(setup).add_link("SR-002", "supersedes", Target(record="SR-001"))
    return open_core(setup), old_pin


@pytest.mark.sr("SR-233")
def test_a_superseded_requirements_moved_links_are_retired_not_stale(
        setup: Path, write_record) -> None:
    """SR-164 EX-1: stale rows, validate and stale selection show nothing for the retired one."""
    from plumb import stale

    core, _ = _superseded(setup, write_record)
    assert _state(core, "SR-001#0").state == "retired"
    assert [r for r in stale.stale_rows(core) if r.link.startswith("SR-001")] == []
    assert links._select_stale(core, "SR-001") == []
    assert "SR-001#0" not in str(core.status())


@pytest.mark.sr("SR-233")
def test_repin_all_stale_leaves_a_retired_pin(setup: Path, write_record) -> None:
    core, old_pin = _superseded(setup, write_record)
    assert links.repin(core, all_stale=True) == []
    assert open_core(setup).index()["SR-001"].links[0].pin == old_pin


@pytest.mark.sr("SR-233")
def test_superseding_names_the_examples_a_test_still_verifies(
        setup: Path, write_record, capsys) -> None:
    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    (setup / "tests").mkdir()
    (setup / "tests" / "test_a.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    from plumb import cli

    root = ["--root", str(setup)]
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_a.py", "--example", "EX-1",
                     *root]) == 0
    assert cli.main(["link", "SR-002", "supersedes", "SR-001", *root]) == 0
    assert ("SR-001/EX-1 is still verified by tests/test_a.py: retire the test too"
            in capsys.readouterr().out)


def test_pin_on_an_uncommitted_edit_keeps_its_version_for_end_texts(setup: Path) -> None:
    """SR-166 EX-2: the pinned version survives being edited again and committed."""
    from tests.conftest import git

    core = open_core(setup)
    git(setup, "add", "-A")
    git(setup, "commit", "-q", "-m", "mod")
    (setup / "src" / "mod.py").write_bytes(b"x = 2\n")          # uncommitted edit
    link = core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    (setup / "src" / "mod.py").write_bytes(b"x = 3\n")
    git(setup, "add", "-A")
    git(setup, "commit", "-q", "-m", "later")
    pinned = open_core(setup).index()["SR-001"].links[0]
    assert pinned.id == link.id
    assert links.end_texts(setup, pinned) == ("x = 2\n", "x = 3\n")


def test_end_texts_finds_a_pin_made_on_the_incoming_side_of_a_merge(setup: Path) -> None:
    """A link pinned on the branch being merged in keeps its version before the merge commits."""
    from tests.conftest import git

    git(setup, "add", "-A")
    git(setup, "commit", "-q", "-m", "mod")
    base = git(setup, "rev-parse", "--abbrev-ref", "HEAD").strip()
    git(setup, "checkout", "-q", "-b", "other")
    (setup / "src" / "mod.py").write_bytes(b"x = 2\n")
    git(setup, "add", "-A")
    git(setup, "commit", "-q", "-m", "two")
    open_core(setup).add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    git(setup, "add", "-A")
    git(setup, "commit", "-q", "-m", "link")
    git(setup, "checkout", "-q", base)
    git(setup, "merge", "-q", "--no-ff", "--no-commit", "other")
    (setup / "src" / "mod.py").write_bytes(b"x = 3\n")
    pinned = open_core(setup).index()["SR-001"].links[0]
    assert links.end_texts(setup, pinned) == ("x = 2\n", "x = 3\n")


def test_pin_on_a_committed_file_stores_no_blob(setup: Path) -> None:
    from tests.conftest import git

    git(setup, "add", "-A")
    git(setup, "commit", "-q", "-m", "mod")
    open_core(setup).add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    assert not list((setup / ".git" / "plumb").glob("pin_blobs.json"))


@pytest.mark.sr("SR-233")
def test_status_and_validate_work_on_a_confirmed_superseded_record_with_a_test(
        setup: Path, write_record) -> None:
    """A retired link has no current pin: status, changed_tests and validate must not read one."""
    from plumb import approvals
    from plumb.validate import validate

    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    (setup / "tests").mkdir()
    (setup / "tests" / "test_a.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    core = open_core(setup)
    core.add_link("SR-001", "verified_by", Target(path="tests/test_a.py"), "EX-1")
    approvals.approve(open_core(setup), ["SR-001"])
    open_core(setup).add_link("SR-002", "supersedes", Target(record="SR-001"))
    core = open_core(setup)
    status = core.status(["SR-001"])["SR-001"]
    assert status.superseded_by == "SR-002" and status.changed_tests == ()
    assert [s.state for s in status.links] == ["retired"]
    assert core.status() and validate(core) is not None


@pytest.mark.sr("SR-233")
def test_an_older_record_superseding_a_newer_one_does_not_retire_it(
        setup: Path, write_record) -> None:
    """SR-076 over SR-150: the owner has not settled it (INT-058 A-1), so SR-150 stays tracked."""
    from plumb.query import retired_ids

    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    open_core(setup).add_link("SR-001", "supersedes", Target(record="SR-002"))
    open_core(setup).add_link("SR-002", "supersedes", Target(record="SR-001"))
    assert retired_ids(open_core(setup).index()) == {"SR-001"}


def test_a_test_the_superseder_already_verifies_is_not_named(
        setup: Path, write_record, capsys) -> None:
    """SR-164: a test copied onto the superseder is not a retired example."""
    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    (setup / "tests").mkdir()
    (setup / "tests" / "test_a.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    from plumb import cli

    root = ["--root", str(setup)]
    for sr in ("SR-001", "SR-002"):
        assert cli.main(["link", sr, "verified_by", "tests/test_a.py", "--example", "EX-1",
                         *root]) == 0
    assert cli.main(["link", "SR-002", "supersedes", "SR-001", *root]) == 0
    assert "still verified" not in capsys.readouterr().out
    from plumb.validate import validate

    assert not [f for f in validate(open_core(setup)) if f.code == "retired-example"]


def test_a_retired_example_is_a_warning_naming_both_records_and_the_test(
        setup: Path, write_record, capsys) -> None:
    """SR-164: the owner's per-pair choice, so validate warns and still exits 0."""
    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    (setup / "tests").mkdir()
    (setup / "tests" / "test_a.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    from plumb import cli

    root = ["--root", str(setup)]
    assert cli.main(["link", "SR-001", "verified_by", "tests/test_a.py", "--example", "EX-1",
                     *root]) == 0
    assert cli.main(["link", "SR-002", "supersedes", "SR-001", *root]) == 0
    capsys.readouterr()
    assert cli.main(["validate", "--json", *root]) == 0
    (warning,) = [w for w in json.loads(capsys.readouterr().out)["warnings"]
                  if w["code"] == "retired-example"]
    assert all(name in warning["message"] for name in ("SR-001/EX-1", "SR-002", "tests/test_a.py"))
    # DEC-065: the test is retired with the example, never moved or kept
    assert "unlink" in warning["message"] and "move it" not in warning["message"]


def test_every_test_of_a_retired_example_is_warned_not_only_the_last(
        setup: Path, write_record) -> None:
    """DEC-065: two tests of one retired example are two warnings."""
    write_record(setup, SR.replace("SR-001", "SR-002").replace("Links pin both ends", "New"))
    (setup / "tests").mkdir()
    for name in ("test_a.py", "test_b.py"):
        (setup / "tests" / name).write_text("def test_x():\n    pass\n", encoding="utf-8")
        open_core(setup).add_link("SR-001", "verified_by", Target(path=f"tests/{name}"), "EX-1")
    open_core(setup).add_link("SR-002", "supersedes", Target(record="SR-001"))
    assert links.live_examples(open_core(setup), "SR-001", "SR-002") == [
        ("EX-1", "tests/test_a.py"), ("EX-1", "tests/test_b.py")]
