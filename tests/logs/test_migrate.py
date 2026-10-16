"""SP6 6.5: ``plumb log migrate`` keeps every digest, chain and evidence identity (SR-074)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from logutil import entries, entry_files, legacy_entry, write_legacy

from logs.gitrepo import add_worktree, commit_all, make_repo, run_git
from plumb import cli, log
from plumb.api import open_core
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-232")

SR = ("---\nid: SR-001\ntitle: Requirement\nstatement: s\nexamples:\n"
      "  - {id: EX-1, given: g, when: w, then: t}\n---\n")


def _chain(n: int, kind: str = "repin", start: int = 0) -> list[dict]:
    out: list[dict] = []
    prev = None
    for i in range(start, start + n):
        raw = legacy_entry(kind, {"i": i}, prev, at=f"2026-10-05T12:{i // 60:02d}:{i % 60:02d}Z")
        out.append(raw)
        prev = raw["digest"]
    return out


def _evidence(prev: str | None, run_id: str, node: str, at: str) -> dict:
    return legacy_entry("test-run", {
        "run_id": run_id, "env": {"env_key": "E"},
        "nodes": [{"id": node, "outcome": "passed", "closure": "C", "test_hash": "T"}]},
        prev, at=at)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    return make_repo(tmp_path / "r")


def test_digests_and_prev_unchanged(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-074 EX-1: every line becomes a file with its digest and prev; validate is clean."""
    events = _chain(30)
    runs = [_evidence(None, "r1", "t.py::a", "2026-10-05T13:00:00Z")]
    runs.append(_evidence(runs[0]["digest"], "r2", "t.py::b", "2026-10-05T13:00:01Z"))
    write_legacy(root, "events", events)
    write_legacy(root, "evidence", runs)
    before = {s: [(e["digest"], e["prev"]) for e in entries(root, s)]
              for s in ("events", "evidence")}
    assert cli.main(["log", "migrate", "--json", "--root", str(root)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["lines"] == 32 and len(data["written"]) == 32 and data["remaining"] == 0
    assert sorted(data["truncated"]) == ["events.jsonl", "evidence.jsonl"]
    paths = PlumbPaths(root)
    assert paths.log_events.exists() and paths.log_events.stat().st_size == 0  # emptied
    assert len(entry_files(root)) == 32
    after = {s: [(e["digest"], e["prev"]) for e in entries(root, s)]
             for s in ("events", "evidence")}
    assert after == before
    for name in entry_files(root):
        raw = json.loads((paths.log_dir / name).read_text(encoding="utf-8"))
        assert raw == next(r for r in events + runs if r["digest"] == raw["digest"])
        assert log.is_migrated_name(name.split("/", 1)[1])
    for stream in ("events", "evidence"):
        assert log.verify_chain(paths, stream) == []
    assert not [f for f in __import__("plumb.validate", fromlist=["validate"])
                .validate(open_core(root)) if f.severity == "error"]


def test_second_run_writes_nothing(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SR-074 EX-2."""
    write_legacy(root, "events", _chain(5))
    assert log.migrate(PlumbPaths(root), dry_run=False).written
    before = {n: (PlumbPaths(root).log_dir / n).stat().st_mtime_ns for n in entry_files(root)}
    again = log.migrate(PlumbPaths(root), dry_run=False)
    assert again.written == () and again.lines == 0 and again.truncated == ()
    after = {n: (PlumbPaths(root).log_dir / n).stat().st_mtime_ns for n in entry_files(root)}
    assert after == before


def test_independent_migrations_merge_clean(root: Path, tmp_path: Path) -> None:
    write_legacy(root, "events", _chain(6))
    commit_all(root, "legacy log")
    other = add_worktree(root, tmp_path / "other", "feat-x")
    assert log.migrate(PlumbPaths(root), dry_run=False).refused == ()
    open_core(root).log_append("events", "repin", {"side": "main"})
    commit_all(root, "migrate on main")
    assert log.migrate(PlumbPaths(other), dry_run=False).refused == ()
    open_core(other).log_append("events", "repin", {"side": "feat"})
    commit_all(other, "migrate on feat")
    merged = run_git(root, "merge", "--no-edit", "feat-x", check=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    names = entry_files(root)
    assert len(names) == 8 and len(set(names)) == 8  # six shared files, one per side
    assert len({e["digest"] for e in entries(root, "events")}) == 8
    assert log.verify_chain(PlumbPaths(root), "events") == []


def test_pre_migration_branch_merges_then_migrates(root: Path, tmp_path: Path) -> None:
    """SR-074 EX-3: a branch made before the migration appends two JSONL lines; after the
    migration on main it merges without conflict, readers see both lines, and the next
    migration moves them."""
    chain = _chain(4)
    write_legacy(root, "events", chain)
    commit_all(root, "legacy log")
    old = add_worktree(root, tmp_path / "old", "old-branch")
    late = _chain(2, start=10)
    late[0] = legacy_entry("repin", {"i": 10}, chain[-1]["digest"], at="2026-10-05T12:00:10Z")
    late[1] = legacy_entry("repin", {"i": 11}, late[0]["digest"], at="2026-10-05T12:00:11Z")
    write_legacy(old, "events", late)  # the old code still appends to the JSONL
    commit_all(old, "old branch appends")
    log.migrate(PlumbPaths(root), dry_run=False)
    commit_all(root, "migrate")
    merged = run_git(root, "merge", "--no-edit", "old-branch", check=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    paths = PlumbPaths(root)
    # git's union merge sees the emptied lines and the appended ones as one adjacent hunk
    # and keeps both sides: the old lines come back next to the new ones. Readers dedupe
    # them by digest against the migrated files, so every entry is read once.
    assert log.legacy_count(paths) == 6
    assert [e["payload"]["i"] for e in entries(root, "events")] == [0, 1, 2, 3, 10, 11]
    assert log.verify_chain(paths, "events") == []
    report = log.migrate(paths, dry_run=False)
    assert len(report.written) == 2 and report.remaining == 0
    assert [e["payload"]["i"] for e in entries(root, "events")] == [0, 1, 2, 3, 10, 11]


def test_evidence_reuse_identical_before_after(root: Path) -> None:
    """SR-074 EX-4: the reuse index and every node's evidence are unchanged."""
    from plumb.verify.evidence import load_index

    runs = [_evidence(None, "r1", "t.py::a", "2026-10-05T13:00:00Z")]
    runs.append(_evidence(runs[0]["digest"], "r2", "t.py::b", "2026-10-05T13:00:01Z"))
    runs.append(_evidence(runs[1]["digest"], "r3", "t.py::a", "2026-10-05T13:00:02Z"))
    write_legacy(root, "evidence", runs)
    before = load_index(open_core(root))
    log.migrate(PlumbPaths(root), dry_run=False)
    after = load_index(open_core(root))
    assert after["nodes"] == before["nodes"] and after["full"] == before["full"]
    assert after["applied"] == before["applied"]
    assert after["nodes"]["t.py::a"]["last"]["run_id"] == "r3"


def test_approvals_and_confirmations_unchanged(root: Path) -> None:
    from plumb import approvals

    (root / ".plumb" / "requirements" / "SR-001.md").write_text(SR, encoding="utf-8")
    core = open_core(root)
    core.log_append("events", "prompt", {"digest": "sha256:p"})
    approvals.approve(open_core(root), ["SR-001"])
    # put the same entries back as legacy lines, as an unmigrated repository has them
    paths = PlumbPaths(root)
    raws = [json.loads((paths.log_dir / n).read_text(encoding="utf-8"))
            for n in entry_files(root)]
    raws.sort(key=lambda r: (r["prev"] is not None, r["at"]))
    for name in entry_files(root):
        (paths.log_dir / name).unlink()
    paths.log_head.unlink()
    write_legacy(root, "events", raws)
    before = open_core(root).status(["SR-001"])["SR-001"]
    assert before.confirmation == "confirmed"
    log.migrate(paths, dry_run=False)
    after = open_core(root).status(["SR-001"])["SR-001"]
    assert after == before


def test_bad_line_refuses_and_writes_nothing(root: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    """SR-074 EX-5: a hand-edited legacy line refuses the run, named, and nothing is written."""
    chain = _chain(3)
    write_legacy(root, "events", chain)
    paths = PlumbPaths(root)
    text = paths.log_events.read_text(encoding="utf-8").replace('"i":1', '"i":7')
    paths.log_events.write_text(text, encoding="utf-8")
    before = paths.log_events.read_bytes()
    assert cli.main(["log", "migrate", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "events.jsonl line 2" in out
    assert entry_files(root) == [] and paths.log_events.read_bytes() == before


def test_check_exits_1_while_legacy_lines_remain(root: Path,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    write_legacy(root, "events", _chain(2))
    assert cli.main(["log", "migrate", "--check", "--root", str(root)]) == 1
    assert "2" in capsys.readouterr().out
    assert entry_files(root) == []
    log.migrate(PlumbPaths(root), dry_run=False)
    assert cli.main(["log", "migrate", "--check", "--root", str(root)]) == 0


def test_dry_run_writes_nothing(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_legacy(root, "events", _chain(3))
    paths = PlumbPaths(root)
    before = paths.log_events.read_bytes()
    assert cli.main(["log", "migrate", "--dry-run", "--json", "--root", str(root)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["written"]) == 3 and data["dry_run"] is True
    assert entry_files(root) == [] and paths.log_events.read_bytes() == before


def test_init_creates_no_jsonl(tmp_path: Path) -> None:
    from plumb.commands import init_repo

    init_repo(tmp_path)
    paths = PlumbPaths(tmp_path)
    assert paths.log_dir.is_dir()
    assert not paths.log_events.exists() and not paths.log_evidence.exists()
    attributes = (paths.plumb / ".gitattributes").read_text(encoding="utf-8")
    assert "log/*.jsonl merge=union" in attributes  # kept for the transition
