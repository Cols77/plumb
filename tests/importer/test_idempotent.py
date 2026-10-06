"""I2: idempotent apply, updates under the plumb ID, re-pinned links (next-plan 9.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from importer_helpers import make_source, plumb_files, rewrite, snapshot, write

from plumb.api import open_core
from plumb.importer.pi_factory import import_pi_factory

pytestmark = pytest.mark.sr("SR-060")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_source(tmp_path)


def _code(repo: Path) -> None:
    write(repo, "src/substrate/judgment/model.py", "class JudgmentRecord:\n    pass\n")
    write(repo, "tests/unit/substrate/judgment/test_evidence_record.py",
          "def test_digest():\n    assert True\n")
    write(repo, "tests/unit/coherence/test_artifact_families.py",
          "def test_spec_nodes():\n    assert True\n")


def test_second_run_no_change(repo: Path, source: Path) -> None:
    _code(repo)
    first = import_pi_factory(open_core(repo), source)
    assert first["actions"]["create"] >= 5
    events = [e.digest for e in open_core(repo).log_read("events")]
    before = plumb_files(repo)
    second = import_pi_factory(open_core(repo), source)
    assert second["actions"]["create"] == second["actions"]["update"] == 0
    assert second["actions"]["unchanged"] == first["actions"]["create"]
    assert plumb_files(repo) == before
    assert [e.digest for e in open_core(repo).log_read("events")] == events


def test_changed_source_updates_and_repins(repo: Path, source: Path) -> None:
    _code(repo)
    import_pi_factory(open_core(repo), source)
    core = open_core(repo)
    old = core.index()["SR-003"]
    # a plumb-side link the importer does not own survives an update, re-pinned
    write_int = repo / ".plumb" / "intents" / "INT-001.md"
    write_int.parent.mkdir(parents=True, exist_ok=True)
    write_int.write_text("---\nid: INT-001\ntitle: Specs as nodes\nquote: specs\n---\n",
                         encoding="utf-8")
    from plumb.contracts import Target

    open_core(repo).add_link("SR-003", "derives_from", Target(record="INT-001"))
    rewrite(source / "requirements" / "SR-003.md", "failing deterministically",
            "failing loudly")
    report = import_pi_factory(open_core(repo), source)
    assert report["actions"]["update"] == 1
    assert "update SR-003" in "\n".join(report["diff"])
    core = open_core(repo)
    new = core.index()["SR-003"]
    assert new.path == old.path and new.hash != old.hash
    assert "failing loudly" in new.fields["statement"]
    assert new.fields["source"]["path"] == "requirements/SR-003.md"
    states = core.link_states(["SR-003"])
    assert states and all(s.state == "current" for s in states)
    assert any(s.link.kind == "derives_from" for s in states)
    assert core.status(["SR-003"])["SR-003"].confirmation == "proposed"
    [entry] = [e for e in core.log_read("events") if e.kind == "import"][1:]
    assert entry.payload["updated"] == ["SR-003"]


def test_never_writes_source_tree(repo: Path, source: Path) -> None:
    _code(repo)
    before = snapshot(source)
    import_pi_factory(open_core(repo), source)
    rewrite(source / "requirements" / "SR-003.md", "failing deterministically",
            "failing loudly")
    changed = snapshot(source)
    import_pi_factory(open_core(repo), source, dry_run=True)
    import_pi_factory(open_core(repo), source)
    assert snapshot(source) == changed and changed != before


def test_two_imports_into_copies_give_identical_trees(tmp_path: Path, repo: Path,
                                                      source: Path) -> None:
    import shutil

    _code(repo)
    twin = tmp_path / "twin"
    shutil.copytree(repo, twin)
    import_pi_factory(open_core(repo), source)
    import_pi_factory(open_core(twin), source)

    def contents(root: Path) -> dict[str, bytes]:
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in sorted((root / ".plumb").rglob("*.md"))}

    assert contents(repo) == contents(twin)
