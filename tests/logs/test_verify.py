"""SP6 6.4: ``verify_chain`` over both formats, naming the file (SR-073, SR-074)."""

from __future__ import annotations

from pathlib import Path

import pytest
from logutil import delete, legacy_entry, tamper, write_legacy

from plumb import log
from plumb.api import open_core
from plumb.normalize import canonical_json
from plumb.paths import PlumbPaths


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlumbPaths:
    monkeypatch.delenv("PLUMB_AGENT_SESSION", raising=False)
    p = PlumbPaths(tmp_path)
    p.log_dir.mkdir(parents=True)
    return p


@pytest.mark.sr("SR-232")
def test_edited_entry_reported_by_file(repo: Path) -> None:
    """SR-073 EX-3: a committed entry file edited by hand is reported as modified."""
    from plumb.validate import validate

    core = open_core(repo)
    core.log_append("events", "approval", {"records": [{"id": "SR-001", "hash": "h"}]})
    core.log_append("events", "repin", {})
    name = tamper(repo, "events", 0, lambda t: t.replace("SR-001", "SR-002"))
    problems = log.verify_chain(core.paths, "events")
    assert problems == [f"{name}: digest does not match the entry (modified entry)"]
    findings = [f for f in validate(open_core(repo)) if f.code == "log"]
    assert any(name in f.message and f.severity == "error" for f in findings)


@pytest.mark.sr("SR-232")
def test_deleted_entry_named_by_prev_not_reported(paths: PlumbPaths) -> None:
    """SR-232 EX-5: verify reports no log error; the merge check refuses the deletion (SR-322)."""
    for i in range(3):
        log.append(paths, "events", "repin", {"i": i})
    delete(paths.root, "events", 1)
    assert log.verify_chain(paths, "events") == []


@pytest.mark.sr("SR-232")
def test_unparsable_file_reported(paths: PlumbPaths) -> None:
    log.append(paths, "events", "repin", {})
    bad = paths.log_kind_dir("repin") / "20261005T120000.000001Z-0badf11e.json"
    bad.write_text("{oops", encoding="utf-8")
    stray = paths.log_kind_dir("repin") / "notes.json"
    stray.write_text("{}", encoding="utf-8")
    array = paths.log_kind_dir("repin") / "20261005T120000.000002Z-0badf11e.json"
    array.write_text("[1]", encoding="utf-8")
    problems = log.verify_chain(paths, "events")
    assert f"repin/{bad.name}: not valid JSON" in problems
    assert any(p.startswith("repin/notes.json: not an entry file name") for p in problems)
    assert f"repin/{array.name}: not a JSON object" in problems
    assert len(list(log.read(paths, "events"))) == 1  # readers skip them


@pytest.mark.sr("SR-232")
def test_forked_chain_accepted(paths: PlumbPaths) -> None:
    base = log.append(paths, "events", "repin", {"base": True})
    # two branches each appended after base: two entries with the same prev
    for side in ("a", "b"):
        raw = legacy_entry("repin", {"side": side}, base.digest, at="2026-10-05T12:00:00Z")
        directory = paths.log_kind_dir("repin")
        (directory / f"20261005T120000.00000{1 if side == 'a' else 2}Z-0000000{side}.json"
         ).write_bytes(canonical_json(raw) + b"\n")
    assert log.verify_chain(paths, "events") == []
    assert len(list(log.read(paths, "events"))) == 3


@pytest.mark.sr("SR-232")
def test_migrated_suffix_must_match_digest(paths: PlumbPaths) -> None:
    raw = legacy_entry("repin", {}, None)
    good = log.migrated_name(raw)
    wrong = good[:-13] + "00000000.json"
    (paths.log_kind_dir("repin")).mkdir(parents=True)
    (paths.log_kind_dir("repin") / wrong).write_bytes(canonical_json(raw) + b"\n")
    problems = log.verify_chain(paths, "events")
    assert problems == [f"repin/{wrong}: migrated name does not match the entry's digest"]


@pytest.mark.sr("SR-232")
def test_legacy_lines_still_checked(paths: PlumbPaths) -> None:
    """During the transition a legacy line edited, deleted or reordered is still reported."""
    first = legacy_entry("repin", {"i": 0}, None)
    second = legacy_entry("repin", {"i": 1}, first["digest"], at="2026-10-05T12:00:01Z")
    third = legacy_entry("repin", {"i": 2}, second["digest"], at="2026-10-05T12:00:02Z")
    write_legacy(paths.root, "events", [first, second, third])
    assert log.verify_chain(paths, "events") == []
    tamper(paths.root, "events", 0, lambda t: t.replace('"i":0', '"i":9'))
    assert any("events.jsonl line 1" in p and "digest" in p
               for p in log.verify_chain(paths, "events"))
    paths.log_events.unlink()
    write_legacy(paths.root, "events", [second, first, third])
    assert any("events.jsonl line 1" in p and "prev" in p
               for p in log.verify_chain(paths, "events"))
