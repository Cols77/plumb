"""SP6 6.3: a cold read never opens the entry files git has just written one by one (SR-073).

Guarantee: wherever git writes many entry files into a worktree, the first read there takes
them from another worktree's pack cache or from git's object store, never by a first open of
each file (about 7 ms per file on Windows: seconds, past the hook ceiling). One test per entry
point: a new worktree (with and without a warm sibling), a new clone (CRLF checkout), a merge
that brings many entries, a deleted pack cache, and ``plumb log migrate``. Entry files git did
not write (untracked appends, an edited file) are still read from disk."""

from __future__ import annotations

from pathlib import Path

import pytest
from logutil import legacy_entry, write_legacy

from logs.gitrepo import add_worktree, commit_all, make_repo, run_git
from logs.test_read_cost import populate
from plumb import log
from plumb.paths import PlumbPaths

pytestmark = pytest.mark.sr("SR-232")

N = 40  # well above log.GIT_BATCH_MIN


@pytest.fixture
def direct_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every entry file the reader opens itself."""
    opened: list[str] = []
    real = log._read_file

    def counting(path: str) -> bytes:
        opened.append(path)
        return real(path)

    monkeypatch.setattr(log, "_read_file", counting)
    return opened


def _digests(root: Path) -> list[str]:
    return [entry.digest for entry in log.read(PlumbPaths(root), "events")]


def _committed(tmp_path: Path, n: int = N) -> Path:
    main = make_repo(tmp_path / "main")
    populate(PlumbPaths(main), n)
    commit_all(main, f"{n} events")
    return main


def _expected(root: Path) -> list[str]:
    """The stream read straight from the files (no pack cache, no git)."""
    return [entry.digest for entry in log._ordered([
        (((raw.get("at", ""), 1, *log._sort_name(name), 0)), log._to_entry("events", raw, -1,
                                                                             name))
        for name, raw in ((f"{p.parent.name}/{p.name}", log._parse_entry(p.read_bytes()))
                          for p in PlumbPaths(root).log_dir.glob("*/*.json"))
        if raw is not None and log.stream_of(str(raw.get("kind"))) == "events"])]


def test_new_worktree_takes_entries_from_a_warm_sibling(
        tmp_path: Path, direct_reads: list[str]) -> None:
    main = _committed(tmp_path)
    expected = _digests(main)  # main's hooks have read its log: its pack cache is warm
    direct_reads.clear()
    wt = add_worktree(main, tmp_path / "wt", "wt")
    assert _digests(wt) == expected
    assert direct_reads == []


def test_new_worktree_without_a_warm_sibling_reads_from_git(
        tmp_path: Path, direct_reads: list[str]) -> None:
    main = _committed(tmp_path)
    wt = add_worktree(main, tmp_path / "wt", "wt")
    assert not PlumbPaths(main).log_pack("events").exists()
    assert _digests(wt) == _expected(wt)
    assert direct_reads == []


def test_new_clone_with_crlf_checkout_reads_from_git(
        tmp_path: Path, direct_reads: list[str]) -> None:
    main = _committed(tmp_path)
    clone = tmp_path / "clone"
    run_git(tmp_path, "clone", "-q", "-c", "core.autocrlf=true", main.as_uri(), str(clone))
    sample = next(PlumbPaths(clone).log_dir.glob("*/*.json")).read_bytes()
    assert sample.endswith(b"\r\n")  # sizes on disk differ from the blobs
    assert _digests(clone) == _expected(main)
    assert direct_reads == []


def test_merge_bringing_many_entries_reads_them_from_git(
        tmp_path: Path, direct_reads: list[str]) -> None:
    main = _committed(tmp_path)
    _digests(main)  # warm
    feat = add_worktree(main, tmp_path / "feat", "feat")
    populate(PlumbPaths(feat), N, start=1000)  # written, never read on that side
    commit_all(feat, "more events")
    run_git(main, "merge", "-q", "--no-edit", "feat")
    direct_reads.clear()
    assert len(_digests(main)) == 2 * N
    assert direct_reads == []


def test_deleted_pack_cache_rebuilt_from_git(tmp_path: Path, direct_reads: list[str]) -> None:
    main = _committed(tmp_path)
    expected = _digests(main)
    PlumbPaths(main).log_pack("events").unlink()
    direct_reads.clear()
    assert _digests(main) == expected
    assert direct_reads == []


@pytest.mark.sr("SR-232")
def test_migrate_leaves_a_warm_pack(tmp_path: Path, direct_reads: list[str]) -> None:
    main = make_repo(tmp_path / "main")
    prev = None
    raws = []
    for i in range(N):
        raw = legacy_entry("mod-hello", {"i": i}, prev, at=f"2026-10-05T12:00:{i:02d}Z")
        raws.append(raw)
        prev = raw["digest"]
    write_legacy(main, "events", raws)
    assert not log.migrate(PlumbPaths(main), dry_run=False).refused
    direct_reads.clear()
    assert _digests(main) == [raw["digest"] for raw in raws]
    assert direct_reads == []


def test_untracked_and_edited_entry_files_read_from_disk(
        tmp_path: Path, direct_reads: list[str]) -> None:
    main = _committed(tmp_path)
    paths = PlumbPaths(main)
    populate(paths, 20, start=5000)  # new entries nobody committed yet
    edited = sorted(paths.log_dir.glob("mod-hello/*.json"))[0]
    edited.write_bytes(edited.read_bytes().replace(b'"quote":"ok, confirm it"',
                                                   b'"quote":"edited in place!"'))
    entries = list(log.read(paths, "events"))
    assert len(entries) == N + 20
    assert len(direct_reads) == 21
    assert next(e for e in entries if e.name == f"mod-hello/{edited.name}").payload["quote"] \
        == "edited in place!"
    assert any("modified entry" in p for p in log.verify_chain(paths, "events"))
