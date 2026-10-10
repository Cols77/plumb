"""One hook process computes statuses and link states once (SR-014): inside
``hashing.stat_cached`` the core keeps them until a record, the events or a link target
changes; outside it every call is exact."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from plumb import api, hashing
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-014")

SR = ("---\nid: SR-001\ntitle: t\nstatement: s\nexamples:\n- {id: EX-1, given: g, when: w, "
      "then: t}\n---\n")


@pytest.fixture
def root(repo: Path, write_record) -> Path:
    write_record(repo, SR)
    (repo / "src").mkdir()
    code = repo / "src" / "m.py"
    code.write_text("X = 1\n", encoding="utf-8")
    old = time.time() - 60
    os.utime(code, (old, old))
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/m.py"))
    return repo


@pytest.fixture
def hashed(monkeypatch: pytest.MonkeyPatch) -> list[Target]:
    calls: list[Target] = []
    real = api._hash_target

    def counted(root, index, target):
        calls.append(target)
        return real(root, index, target)

    monkeypatch.setattr(api, "_hash_target", counted)
    return calls


def test_statuses_are_computed_once_per_process(root: Path, hashed: list[Target]) -> None:
    core = open_core(root)
    with hashing.stat_cached(root):
        first = core.status()
        n = len(hashed)
        assert n >= 1
        assert core.status() == first
        assert core.status(["SR-001"]) == {"SR-001": first["SR-001"]}
        assert core.link_states(["SR-001"]) == list(first["SR-001"].links)
        assert len(hashed) == n


def test_nothing_is_kept_outside_a_hook_process(root: Path, hashed: list[Target]) -> None:
    core = open_core(root)
    core.status()
    n = len(hashed)
    core.status()
    assert len(hashed) == 2 * n


def test_a_record_write_invalidates(root: Path, hashed: list[Target], write_record) -> None:
    core = open_core(root)
    with hashing.stat_cached(root):
        assert core.status()["SR-001"].confirmation == "proposed"
        core.write_record("requirement", {"title": "t", "statement": "changed",
                                          "examples": [{"id": "EX-1", "given": "g",
                                                        "when": "w", "then": "t"}],
                                          "links": [{"kind": "implemented_by",
                                                     "path": "src/m.py"}]},
                          record_id="SR-001")
        n = len(hashed)
        after = core.status()["SR-001"]
        assert len(hashed) > n
        assert after.links[0].state == "unpinned"  # the rewritten record has no pin


def test_a_changed_link_target_invalidates(root: Path) -> None:
    core = open_core(root)
    with hashing.stat_cached(root):
        assert core.status()["SR-001"].links[0].state == "current"
        (root / "src" / "m.py").write_text("X = 2\n", encoding="utf-8")
        hashing.forget_ends()
        assert core.status()["SR-001"].links[0].state == "stale"


def test_a_new_event_invalidates(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import confirm

    runs: list[int] = []
    real = confirm.remaining_entries

    def counted(*args, **kwargs):
        runs.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(confirm, "remaining_entries", counted)
    core = open_core(root)
    with hashing.stat_cached(root):
        core.status()
        core.status()
        assert len(runs) == 1
        core.log_append("events", "note", {"x": 1})
        core.status()
        assert len(runs) == 2


def test_a_file_end_is_hashed_once_per_process(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (root / "src" / "n.py").write_text("def a():\n    return 1\n\n\ndef b():\n    return 2\n",
                                       encoding="utf-8")
    reads: list[Path] = []
    real = Path.read_bytes

    def counted(self: Path) -> bytes:
        if self.name == "n.py":
            reads.append(self)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", counted)
    with hashing.stat_cached(root):
        for symbol in ("a", "b", "a", "b"):
            assert hashing.hash_target(root, {}, Target(path="src/n.py", symbol=symbol))
        assert hashing.hash_target(root, {}, Target(path="src/n.py"))
    assert len(reads) <= 2  # the whole-file digest and one parse, never one per end
