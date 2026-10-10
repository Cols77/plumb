"""The link-end hash cache: inside ``hashing.stat_cached`` (the hooks' status snapshot), a
file's hash is reused across processes while its size, times and inode are unchanged, so the
snapshot stays within the hook budget (SR-014); outside it, every end is hashed exactly."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from plumb import hashing
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-014")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".plumb").mkdir()
    (tmp_path / "src").mkdir()
    code = tmp_path / "src" / "m.py"
    code.write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n", encoding="utf-8")
    old = time.time() - 60  # outside the racy window
    os.utime(code, (old, old))
    return tmp_path


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    reads: list[Path] = []
    real = hashing.file_digest

    def counted(path: Path) -> str:
        reads.append(path)
        return real(path)

    monkeypatch.setattr(hashing, "file_digest", counted)
    return reads


def _hash(root: Path, target: Target) -> str | None:
    """One hook process: hash inside the cache, which is saved when the block ends."""
    with hashing.stat_cached(root):
        return hashing.hash_target(root, {}, target)


def test_unchanged_file_is_not_read_again_in_a_later_process(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reads = _counting(monkeypatch)
    target = Target(path="src/m.py")
    first = _hash(root, target)
    assert _hash(root, target) == first
    assert len(reads) == 1


def test_an_edit_is_hashed_again(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = Target(path="src/m.py")
    first = _hash(root, target)
    code = root / "src" / "m.py"
    code.write_text("def f():\n    return 3\n", encoding="utf-8")
    old = time.time() - 30
    os.utime(code, (old, old))
    assert _hash(root, target) != first


def test_a_file_written_just_now_is_not_cached(root: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    code = root / "src" / "m.py"
    code.write_text("def f():\n    return 5\n", encoding="utf-8")  # mtime: now
    reads = _counting(monkeypatch)
    target = Target(path="src/m.py")
    _hash(root, target)
    _hash(root, target)
    assert len(reads) == 2


def test_symbol_hash_is_cached_and_follows_edits(root: Path) -> None:
    target = Target(path="src/m.py", symbol="m:g")
    first = _hash(root, target)
    assert _hash(root, target) == first
    code = root / "src" / "m.py"
    code.write_text("def f():\n    return 1\n\n\ndef g():\n    return 9\n", encoding="utf-8")
    old = time.time() - 30
    os.utime(code, (old, old))
    assert _hash(root, target) != first


def test_a_missing_file_dangles(root: Path) -> None:
    assert hashing.hash_target(root, {}, Target(path="src/gone.py")) is None


def test_outside_the_cache_every_end_is_hashed_exactly(root: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    target = Target(path="src/m.py")
    _hash(root, target)
    reads = _counting(monkeypatch)
    hashing.hash_target(root, {}, target)
    assert len(reads) == 1  # validate, drift and the merge boundary never trust the cache


def test_a_hook_cut_by_the_watchdog_still_saves_what_it_learned(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The watchdog ends the process without leaving the block, so it flushes the cache first:
    otherwise a hook too slow to finish would stay cold every turn."""
    reads = _counting(monkeypatch)
    target = Target(path="src/m.py")
    with hashing.stat_cached(root):
        first = hashing.hash_target(root, {}, target)
        hashing.flush_stat_cache()  # what the watchdog calls just before it exits
        saved = (root / ".plumb" / "cache" / "hashes.json").read_text("utf-8")
    assert "src/m.py" in saved
    assert _hash(root, target) == first
    assert len(reads) == 1
    hashing.flush_stat_cache()  # outside any block: nothing to do, never an error


def test_one_hook_process_looks_at_an_end_once(root: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """The brief and the status snapshot ask for the same ends several times in one hook; the
    block answers repeats from memory instead of statting the file each time."""
    target = Target(path="src/m.py")
    seen: list[str] = []
    real = os.stat

    def counted(path, *args, **kwargs):
        seen.append(str(path))
        return real(path, *args, **kwargs)

    with hashing.stat_cached(root):
        first = hashing.hash_target(root, {}, target)
        monkeypatch.setattr(hashing.os, "stat", counted)
        assert [hashing.hash_target(root, {}, target) for _ in range(3)] == [first] * 3
    assert not [p for p in seen if p.endswith("m.py")]
