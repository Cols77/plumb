"""K6: plumb validate (spec 5.10) and SR trailer parsing (spec 5.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from logutil import tamper

from plumb import approvals, cli, log
from plumb.api import open_core
from plumb.contracts import Target
from plumb.normalize import sha256_text
from plumb.trailers import invalid_ids, parse_sr_trailer
from plumb.validate import validate

pytestmark = pytest.mark.sr("SR-231")

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: r\n---\n"
SR = """---
id: SR-001
title: Links pin both ends
feature: FEAT-001
statement: s
examples:
  - {id: EX-1, given: g, when: w, then: t}
---
"""
FEAT = "---\nid: FEAT-001\ntitle: Core\nrequirements: [SR-001]\n---\n"


@pytest.fixture
def clean(repo: Path, write_record) -> Path:
    for text in (INT, SR, FEAT):
        write_record(repo, text)
    open_core(repo).add_link("SR-001", "derives_from", Target(record="INT-001"))
    return repo


def _codes(root: Path, severity: str) -> list[str]:
    return [f.code for f in validate(open_core(root)) if f.severity == severity]


def test_clean_repo_passes(clean: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _codes(clean, "error") == []
    assert cli.main(["validate", "--root", str(clean)]) == 0
    assert cli.main(["check", "--json", "--root", str(clean)]) == 0
    out = capsys.readouterr().out
    data = json.loads(out[out.index("{"):])
    assert data["errors"] == []
    assert any(w["code"] == "proposed" for w in data["warnings"])


def test_errors_exit_one(clean: Path, write_record) -> None:
    write_record(clean, INT, name="INT-001-copy.md")
    write_record(clean, SR.replace("SR-001", "SR-002").replace("FEAT-001", "FEAT-009"))
    write_record(clean, "---\nid: SR-003\ntitle: t\nstatement: s\nlinks:\n"
                 "  - {kind: derives_from, to: INT-404}\n  - {kind: decides, to: INT-001}\n---\n")
    codes = _codes(clean, "error")
    assert "duplicate" in " ".join(codes) or "load" in codes
    assert "dangling" in codes and "kind" in codes and "feature" in codes
    assert cli.main(["validate", "--root", str(clean)]) == 1


def test_warnings_for_stale_unconfirmed_uncovered(clean: Path, write_record) -> None:
    approvals.approve(open_core(clean), ["SR-001", "INT-001"])
    assert "uncovered" in _codes(clean, "warning")
    path = clean / ".plumb" / "intents" / "INT-001.md"
    path.write_text(INT.replace("readback: r", "readback: r2"), encoding="utf-8")
    write_record(clean, "---\nid: SR-002\ntitle: t\nstatement: s\nlinks:\n"
                 "  - {kind: derives_from, to: INT-001}\n---\n")
    warnings = _codes(clean, "warning")
    assert {"stale", "unconfirmed-edit", "uncovered", "unpinned"} <= set(warnings)
    assert _codes(clean, "error") == []


def test_sr_without_derives_from_warns(clean: Path, write_record) -> None:
    write_record(clean, "---\nid: SR-002\ntitle: t\nstatement: s\n---\n")
    findings = [f for f in validate(open_core(clean)) if f.code == "no-intent"]
    assert [f.subject for f in findings] == ["SR-002"]


def test_matters_false_dec_deciding_confirmed_record_warns(clean: Path, write_record) -> None:
    write_record(clean, "---\nid: DEC-001\ntitle: d\nquestion: q\nchosen: a\nmatters: false\n"
                 "---\n")
    open_core(clean).add_link("DEC-001", "decides", Target(record="SR-001"))
    approvals.approve(open_core(clean), ["SR-001"])
    assert "dec-matters" in _codes(clean, "warning")


def test_owner_approval_under_marker_is_error(clean: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    core = open_core(clean)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    record = core.index()["SR-001"]
    log.append(core.paths, "events", "approval",
               {"records": [{"id": "SR-001", "hash": record.hash}], "by": "owner"})
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert "approval" in _codes(clean, "error")
    assert open_core(clean).status(["SR-001"])["SR-001"].confirmation == "proposed"


def test_relayed_approval_without_prompt_event_is_error(clean: Path) -> None:
    core = open_core(clean)
    record = core.index()["SR-001"]
    log.append(core.paths, "events", "approval",
               {"records": [{"id": "SR-001", "hash": record.hash}], "by": "agent-relayed",
                "prompt_digest": "sha256:" + "a" * 64, "quote": "ok",
                "quote_digest": sha256_text("ok")})
    assert "approval" in _codes(clean, "error")
    assert open_core(clean).status(["SR-001"])["SR-001"].confirmation == "proposed"


def test_tampered_log_line_is_error(clean: Path) -> None:
    approvals.approve(open_core(clean), ["SR-001"])
    tamper(clean, "events", -1, lambda t: t.replace('"owner"', '"import"'))
    assert "log" in _codes(clean, "error")


@pytest.mark.sr("SR-261")
def test_parse_sr_trailer_variants() -> None:
    message = ("core: pin links\n\nMentions SR-009 in prose.\n\nSR: SR-001, SR-002\r\n"
               "SR:SR-003\nSR: SR-001\nCo-Authored-By: x\n")
    assert parse_sr_trailer(message) == ("SR-001", "SR-002", "SR-003")
    assert parse_sr_trailer("no trailer") == ()
    assert invalid_ids(("SR-001", "SR-1", "INT-001", "FEAT-002")) == ("SR-1",)


@pytest.mark.sr("SR-237")
def test_supersedes_a_newer_record_warns(clean: Path, write_record) -> None:
    write_record(clean, "---\nid: SR-002\ntitle: t\nstatement: s\nlinks:\n"
                 "  - {kind: derives_from, to: INT-001}\n---\n")
    write_record(clean, "---\nid: SR-003\ntitle: t3\nstatement: s3\nlinks:\n"
                 "  - {kind: derives_from, to: INT-001}\n---\n")
    from plumb.links import add_link

    add_link(open_core(clean), "SR-003", "supersedes", Target(record="SR-002"))
    assert "supersedes" not in _codes(clean, "warning")
    add_link(open_core(clean), "SR-002", "supersedes", Target(record="SR-003"))
    assert "supersedes" in _codes(clean, "warning")
