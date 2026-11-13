"""report-30e224a3: the worker's turn upkeep reads the log kinds it needs, not the whole log.

Each ``iaso understand worker`` held about 500 MB because its upkeep loaded every entry of
every kind each turn and kept it on the core. A read of some kinds loads those kinds'
payloads only, in the full read's order, and the worker's pass asks for its kinds."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from logutil import legacy_entry
from understand.test_read_job import make_core, record_text

from iaso import approvals, confirm, log
from iaso.api import open_core
from iaso.normalize import canonical_json
from iaso.paths import IasoPaths
from iaso.understand import files, summary

SESSION = "s-upkeep"
FEAT = "---\nid: FEAT-001\ntitle: deadline reminders\n---\n"
NEEDED = ("approval", "calibration", "revocation")
BULK = ("offer", "judgment", "repin", "job-note")     # what fills the log; no upkeep reads it


def put(paths: IasoPaths, raw: dict[str, Any], folder: str | None = None) -> str:
    """Write ``raw`` as an entry file (in its kind's folder unless ``folder``); its name."""
    directory = paths.log_kind_dir(folder or raw["kind"])
    directory.mkdir(parents=True, exist_ok=True)
    name = log.migrated_name(raw)
    (directory / name).write_bytes(canonical_json(raw) + b"\n")
    return f"{folder or raw['kind']}/{name}"


def populate(paths: IasoPaths, kinds: tuple[str, ...], n: int) -> None:
    prev = None
    for i in range(n):
        raw = legacy_entry(kinds[i % len(kinds)], {"i": i, "by": "agent-relayed", "records": []},
                           prev, at=f"2026-10-01T00:{(i // 60) % 60:02d}:{i % 60:02d}Z")
        put(paths, raw)
        prev = raw["digest"]


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The folders whose entry files a reader opened (git's store never answers instead)."""
    seen: list[str] = []
    real = log._read_file

    def spy(path: str) -> bytes:
        seen.append(Path(path).parent.name)
        return real(path)

    monkeypatch.setattr(log, "_read_file", spy)
    monkeypatch.setattr(log, "GIT_BATCH_MIN", 10 ** 9)   # every miss is a counted file read
    return seen


def test_read_kinds_loads_those_kinds_only(repo: Path, opened: list[str]) -> None:
    paths = IasoPaths(repo)
    populate(paths, NEEDED + BULK, 70)
    log.read_kinds(paths, "events", ["approval"])         # a pass before: the chain is known
    del opened[:]
    got = log.read_kinds(paths, "events", ["approval", "revocation"])
    assert {e.kind for e in got} == {"approval", "revocation"}
    assert sum("i" in e.payload for e in got) == 20
    assert set(opened) == {"revocation"}                 # approval's own pack is warm already
    assert not paths.log_pack("events").exists()        # the whole-stream pack is not built
    del opened[:]
    again = log.read_kinds(paths, "events", ["approval", "revocation"])
    assert [e.digest for e in again] == [e.digest for e in got] and opened == []   # warm
    everything = [e for e in log.read(paths, "events") if e.kind in ("approval", "revocation")]
    assert [e.digest for e in everything] == [e.digest for e in got]   # the full read's order


def test_read_kinds_keeps_the_full_order_and_a_misfiled_entry(repo: Path) -> None:
    """A skewed clock chained through another kind places an entry as the full read does,
    and an entry whose own kind differs from its folder is read under its own kind."""
    paths = IasoPaths(repo)
    a = legacy_entry("approval", {"n": "a"}, None, at="2026-10-01T00:00:10Z")
    c = legacy_entry("job-note", {"n": "c"}, a["digest"], at="2026-10-01T00:00:20Z")
    b = legacy_entry("approval", {"n": "b"}, c["digest"], at="2026-10-01T00:00:05Z")  # skewed
    d = legacy_entry("revocation", {"n": "d"}, b["digest"], at="2026-10-01T00:00:30Z")
    for raw in (a, c, b):
        put(paths, raw)
    put(paths, d, folder="job-note")                    # a revocation in another kind's folder
    full = [e.payload["n"] for e in log.read(paths, "events", ["approval", "revocation"])]
    assert full == ["a", "b", "d"]
    assert [e.payload["n"] for e in log.read_kinds(paths, "events",
                                                   ["approval", "revocation"])] == full
    assert [e.payload["n"] for e in log.read_kinds(paths, "events", ["revocation"])] == ["d"]


def _queue(root: Path, turn: dict[str, Any]) -> None:
    files.write_json_atomic(files.session_dir(root, SESSION) / summary.AFTER_STOP,
                            {"turn": turn, "transcript": None})


def test_worker_pass_holds_no_whole_log(repo: Path, write_record, opened: list[str],
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Through ``summary.after_stop`` with a verdict and a judge approval logged this turn:
    the core never holds the whole log, no whole-stream read happens and no bulk kind file is
    opened (once a pass before has seen them)."""
    make_core(repo, write_record, [FEAT, record_text(1, "Reminders before a deadline")])
    approvals.approve(open_core(repo), ["SR-001"])
    paths = IasoPaths(repo)
    populate(paths, BULK, 120)
    core = open_core(repo)                               # the worker's core, kept across passes
    _queue(repo, {"turn_start": time.time() - 60, "prompt_digest": "sha256:" + "0" * 64})
    summary.after_stop(core, SESSION)                    # a turn before
    assert core._events is None
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record_hash = core.index()["SR-001"].hash
    verdict = legacy_entry("verdict", {"records": [{"id": "SR-001", "hash": record_hash}],
                                       "score": 0.9, "session": SESSION}, None, at=now)
    judged = legacy_entry("approval", {"by": "auto-jev", "session": SESSION,
                                       "records": [{"id": "SR-001", "hash": record_hash}],
                                       "auto": {"score": 0.9}}, verdict["digest"], at=now)
    trial = legacy_entry("trial", {"answer": "yes", "session": SESSION}, judged["digest"],
                         at=now)
    for raw in (verdict, judged, trial):
        put(paths, raw)
    whole: list[str] = []
    real_all = log._all_entries
    monkeypatch.setattr(log, "_all_entries",
                        lambda p, s, *a, **k: whole.append(s) or real_all(p, s, *a, **k))
    asked: list[Any] = []
    real_statuses = confirm.statuses
    monkeypatch.setattr(confirm, "statuses",
                        lambda c, ids=None: asked.append(ids) or real_statuses(c, ids))
    del opened[:]
    paths.log_pack("events").unlink(missing_ok=True)    # the setup's full reads built it
    _queue(repo, {"turn_start": time.time() - 30, "prompt_digest": "sha256:" + "0" * 64})
    summary.after_stop(core, SESSION)
    assert ["SR-001"] in asked                           # the judged record's status was read
    assert core._events is None
    assert whole == []
    assert opened and not set(opened) & set(BULK), opened
    assert not paths.log_pack("events").exists()
    assert json.loads(paths.log_chain_pack("events").read_text("utf-8"))["order"]
