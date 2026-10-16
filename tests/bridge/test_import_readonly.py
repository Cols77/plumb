"""BRIDGE BS2: the importer never writes to its source; dry runs write nothing (spec 8.1)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pi_source_fixture import make_pi_source

from plumb import cli
from plumb.api import open_core
from plumb.importer.pi_factory import import_pi_factory, read_head

pytestmark = pytest.mark.sr("SR-238")


@pytest.fixture
def pi_source(tmp_path: Path) -> Path:
    return make_pi_source(tmp_path)


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                             p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def _plumb_files(repo: Path) -> dict[str, tuple[str, int]]:
    return {k: v for k, v in _snapshot(repo / ".plumb").items() if not k.startswith("cache/")}


def test_source_tree_unchanged_after_import(repo: Path, pi_source: Path) -> None:
    before = _snapshot(pi_source)
    import_pi_factory(open_core(repo), pi_source)
    assert _snapshot(pi_source) == before


def test_dry_run_writes_nothing(repo: Path, pi_source: Path) -> None:
    before = _plumb_files(repo)
    report = import_pi_factory(open_core(repo), pi_source, dry_run=True)
    assert report["dry_run"] is True
    assert report["counts"] == {"requirement": 3, "feature": 1, "nc": 1}
    assert _plumb_files(repo) == before


def test_import_event_logged(repo: Path, pi_source: Path) -> None:
    report = import_pi_factory(open_core(repo), pi_source)
    [entry] = list(open_core(repo).log_read("events", kinds=["import"]))
    assert entry.kind == "import"
    payload = entry.payload
    assert payload["source"] == str(pi_source)
    assert payload["head"] == "0123456789abcdef0123456789abcdef01234567"
    assert payload["counts"] == report["counts"]
    assert payload["findings_digest"].startswith("sha256:")
    assert payload["findings"] == len(report["findings"])


def test_read_head_from_packed_refs_and_worktree_file(tmp_path: Path) -> None:
    src = tmp_path / "s"
    (src / ".git").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref: refs/heads/dev\n", encoding="utf-8")
    (src / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled\n" + "a" * 40 + " refs/heads/dev\n", encoding="utf-8")
    assert read_head(src) == "a" * 40
    wt = tmp_path / "wt"
    wt.mkdir()
    gitdir = src / ".git" / "worktrees" / "wt"
    gitdir.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {gitdir.as_posix()}\n", encoding="utf-8")
    (gitdir / "HEAD").write_text("b" * 40 + "\n", encoding="utf-8")
    assert read_head(wt) == "b" * 40
    assert read_head(tmp_path / "none") is None


def test_import_cli(repo: Path, pi_source: Path, capsys) -> None:
    assert cli.main(["import", "pi-agent-factory", str(pi_source), "--dry-run", "--json",
                     "--root", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True and data["counts"]["requirement"] == 3
    assert cli.main(["import", "pi-agent-factory", str(pi_source), "--only", "NC",
                     "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "imported" in out and "proposed" in out
    assert "NC-0002" in open_core(repo).index()
    assert cli.main(["import", "other-tool", str(pi_source), "--root", str(repo)]) == 2
    assert cli.main(["import", "pi-agent-factory", str(pi_source / "nope"),
                     "--root", str(repo)]) == 2
