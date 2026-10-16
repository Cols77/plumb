"""CAPTURE C5: an escalated spec is approved by one set-hash approval (sp2 6.2, SR-037)."""

from __future__ import annotations

from pathlib import Path

import pytest
from capture_helpers import (
    agent_shell_setup,
    event_kinds,
    record_text,
    run,
)

from plumb.api import open_core
from plumb.capture.spec import approve_set, set_hash, set_state

pytestmark = pytest.mark.sr("SR-227")


@pytest.fixture
def spec(repo: Path, write_record) -> Path:
    write_record(repo, record_text("INT-021", "export redesign", quote="redo the export",
                                   readback="Redo the export", mode="escalated",
                                   members=["SR-070", "SR-071"]))
    for n in (70, 71):
        write_record(repo, record_text(f"SR-0{n}", f"export rule {n}",
                                       statement=f"rule {n}",
                                       links=[{"kind": "derives_from", "to": "INT-021"}]))
    return repo


def approvals(repo: Path) -> list:
    return list(open_core(repo).log_read("events", ["approval"]))


def test_set_hash_over_sorted_members(spec: Path, capsys) -> None:
    assert set_state(open_core(spec), "INT-021") == "unapproved"
    assert run(spec, "spec", "show", "INT-021") == 0
    out = capsys.readouterr().out
    assert "SR-070" in out and "SR-071" in out and "set hash: sha256:" in out
    approve_set(open_core(spec), "INT-021")  # the library, the owner's terminal (test)
    [entry] = approvals(spec)
    core = open_core(spec)
    index = core.index()
    pairs = [(i, index[i].hash) for i in ("SR-071", "INT-021", "SR-070")]
    assert entry.payload["set"] == {"anchor": "INT-021", "hash": set_hash(pairs)}
    assert entry.payload["by"] == "owner"
    assert {r["id"] for r in entry.payload["records"]} == {"INT-021", "SR-070", "SR-071"}
    statuses = core.status()
    assert {statuses[i].confirmation for i in ("INT-021", "SR-070", "SR-071")} == {"confirmed"}
    assert set_state(core, "INT-021") == "approved"


@pytest.mark.sr("SR-210")
def test_spec_approve_no_longer_exists(spec: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "session-1")
    assert run(spec, "spec", "approve", "INT-021") == 3
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert run(spec, "spec", "approve", "INT-021") == 3    # the owner's terminal too
    assert "no longer exists" in capsys.readouterr().err
    assert approvals(spec) == []


@pytest.mark.sr("SR-210")
def test_spec_approve_refused_without_terminal(spec: Path, monkeypatch, capsys) -> None:
    agent_shell_setup(monkeypatch)
    assert run(spec, "spec", "approve", "INT-021") == 3
    assert "no longer exists" in capsys.readouterr().err
    assert "approval" not in event_kinds(spec)


def edit_member(repo: Path, record_id: str, old: str, new: str) -> None:
    path = repo / ".plumb" / "requirements" / f"{record_id}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_member_edit_unconfirms_member_and_set(spec: Path) -> None:
    approve_set(open_core(spec), "INT-021")
    path = spec / ".plumb" / "requirements" / "SR-071.md"
    path.write_text(path.read_text(encoding="utf-8").replace("rule 71", "rule 71 changed"),
                    encoding="utf-8")
    core = open_core(spec)
    statuses = core.status()
    assert statuses["SR-071"].confirmation == "unconfirmed-edit"
    assert statuses["SR-070"].confirmation == "confirmed"
    assert set_state(core, "INT-021") == "unconfirmed"


def test_not_a_set(spec: Path, write_record, capsys) -> None:
    write_record(spec, record_text("INT-022", "small thing", quote="x", readback="x"))
    assert run(spec, "spec", "show", "INT-022") == 1
    assert "not an escalated spec" in capsys.readouterr().err

