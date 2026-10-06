"""I1: the import plan and its dry-run diff (next-plan 9.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from importer_helpers import make_source, plumb_files, rewrite, snapshot

from plumb import cli
from plumb.api import open_core
from plumb.importer.pi_factory import import_pi_factory
from plumb.importer.plan import plan_import

pytestmark = pytest.mark.sr("SR-060")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_source(tmp_path)


def _actions(plan) -> dict[str, str]:
    return {item.record_id: item.action for item in plan.records}


def test_dry_run_diff_lists_create_update_skip(repo: Path, source: Path, write_record,
                                               capsys) -> None:
    plan = plan_import(open_core(repo), source)
    assert set(_actions(plan).values()) == {"create"}
    assert {"SR-003", "SR-077", "SR-078", "FEAT-001", "NC-0002"} <= set(_actions(plan))
    import_pi_factory(open_core(repo), source)
    rewrite(source / "requirements" / "SR-003.md", "failing deterministically",
            "failing loudly")
    write_record(repo, "---\nid: NC-0002\ntitle: plumb's own NC\nstatus: open\n---\n")
    # NC-0002 was imported: overwrite it as a record of another origin
    plan = plan_import(open_core(repo), source)
    actions = _actions(plan)
    assert actions["SR-003"] == "update"
    assert actions["SR-077"] == "unchanged"
    assert actions["NC-0002"] == "skip"
    sr003 = next(item for item in plan.records if item.record_id == "SR-003")
    assert [change.field for change in sr003.changes] == ["source", "statement"]
    # the CLI prints the plan as a diff and writes nothing
    before = plumb_files(repo)
    assert cli.main(["import", "pi-agent-factory", str(source), "--dry-run",
                     "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "update SR-003" in out and "~ statement:" in out and "failing loudly" in out
    assert "skip NC-0002" in out and "unchanged SR-077" not in out
    assert "1 unchanged" in out or "unchanged" in out
    assert plumb_files(repo) == before


def test_dry_run_writes_nothing(repo: Path, source: Path, capsys) -> None:
    before_target, before_source = plumb_files(repo), snapshot(source)
    report = import_pi_factory(open_core(repo), source, dry_run=True)
    assert report["dry_run"] is True
    assert report["actions"]["create"] == len(report["diff_records"])
    assert any(line.startswith("create SR-077") for line in report["diff"])
    assert cli.main(["import", "pi-agent-factory", str(source), "--dry-run", "--json",
                     "--root", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True and data["actions"]["create"] >= 5
    assert plumb_files(repo) == before_target
    assert snapshot(source) == before_source
    assert list(open_core(repo).log_read("events")) == []


def test_diff_flag_prints_the_plan_then_applies(repo: Path, source: Path, capsys) -> None:
    assert cli.main(["import", "pi-agent-factory", str(source), "--diff",
                     "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "create SR-077" in out and "imported" in out
    assert "SR-077" in open_core(repo).index()


def test_never_imported_into_plumbs_own_repository(repo: Path, source: Path, capsys) -> None:
    (repo / "pyproject.toml").write_text('[project]\nname = "plumb"\n', encoding="utf-8")
    before = plumb_files(repo)
    assert cli.main(["import", "pi-agent-factory", str(source), "--root", str(repo)]) == 2
    assert "plumb's own repository" in capsys.readouterr().err
    assert plumb_files(repo) == before


def test_findings_counted_by_kind(repo: Path, source: Path) -> None:
    report = import_pi_factory(open_core(repo), source, dry_run=True)
    counts = report["finding_counts"]
    assert counts and sum(counts.values()) == len(report["findings"])
    assert counts.get("missing-end", 0) >= 1
