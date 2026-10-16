"""I5: ``by: import`` approvals only from upstream human consent pinning the current content
(next-plan 9.3, concept 10, R2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from importer_helpers import CONSENT_DIR, make_source, rewrite, write

from plumb.api import open_core
from plumb.importer.pi_factory import import_pi_factory

pytestmark = pytest.mark.sr("SR-238")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_source(tmp_path)


def _approvals(repo: Path) -> list:
    return [e for e in open_core(repo).log_read("events") if e.kind == "approval"]


def _consent(source: Path, sr: str) -> Path:
    return source / CONSENT_DIR / f"{sr}.json"


def _approved_ids(repo: Path) -> list[str]:
    return [str(r["id"]) for e in _approvals(repo) for r in e.payload["records"]]


def test_consent_pinning_current_content_gives_by_import(repo: Path, source: Path) -> None:
    import_pi_factory(open_core(repo), source)
    core = open_core(repo)
    statuses = core.status()
    # SR-077's consent pins the LF form of its file, SR-078's the CRLF form: both current
    for sr in ("SR-077", "SR-078"):
        assert statuses[sr].confirmation == "confirmed"
        assert statuses[sr].approved_by == "import"
    # everything else arrives proposed: features, NCs and SRs without a consent
    others = [s for rid, s in statuses.items() if rid not in ("SR-077", "SR-078")]
    assert others and all(s.confirmation == "proposed" for s in others)
    [approval] = _approvals(repo)
    assert approval.payload["by"] == "import"
    assert _approved_ids(repo) == ["SR-077", "SR-078"]
    assert approval.payload["records"][0]["hash"] == core.index()["SR-077"].hash
    # a second import writes no second approval
    import_pi_factory(open_core(repo), source)
    assert len(_approvals(repo)) == 1


def test_consent_for_older_content_stays_proposed(repo: Path, source: Path) -> None:
    # SR-078 changed upstream after its consent was given
    rewrite(source / "requirements" / "SR-078.md", "Judgment-assisted review triage",
            "Judgment-assisted review sorting")
    report = import_pi_factory(open_core(repo), source)
    assert open_core(repo).status(["SR-078"])["SR-078"].confirmation == "proposed"
    assert any(f["kind"] == "consent-stale" and f["id"] == "SR-078"
               for f in report["findings"])
    assert _approved_ids(repo) == ["SR-077"]
    # an upstream edit of SR-077 after its consent: updated, and no longer confirmed
    rewrite(source / "requirements" / "SR-077.md", "Typed judgment adapter",
            "Typed judgment adaptor")
    import_pi_factory(open_core(repo), source)
    status = open_core(repo).status(["SR-077"])["SR-077"]
    assert status.confirmation == "unconfirmed-edit"
    assert len(_approvals(repo)) == 1


@pytest.mark.parametrize("field, value", [("reviewer", "agent"), ("decision", "reject"),
                                          ("phrase", "I approve."), ("reason", "")])
def test_non_human_or_wrong_phrase_ignored(repo: Path, source: Path, field: str,
                                           value: str) -> None:
    path = _consent(source, "SR-077")
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    report = import_pi_factory(open_core(repo), source)
    assert open_core(repo).status(["SR-077"])["SR-077"].confirmation == "proposed"
    assert "SR-077" not in _approved_ids(repo)
    assert any(f["kind"] == "consent-ignored" and f["id"] == "SR-077"
               for f in report["findings"])


def test_malformed_consent_ignored(repo: Path, source: Path) -> None:
    _consent(source, "SR-077").write_text("{not json", encoding="utf-8")
    write(source, ".factory/planning/OTHER/consent/SR-003.json", json.dumps(
        {"schema": 1, "run_id": "ELSEWHERE", "sr_id": "SR-003"}))
    report = import_pi_factory(open_core(repo), source)
    assert _approved_ids(repo) == ["SR-078"]
    kinds = {(f["kind"], f["id"]) for f in report["findings"]}
    assert ("consent-ignored", "SR-077") in kinds and ("consent-ignored", "SR-003") in kinds


def test_by_import_cites_consent_file_and_digest(repo: Path, source: Path) -> None:
    import hashlib

    import_pi_factory(open_core(repo), source)
    [approval] = _approvals(repo)
    upstream = approval.payload["records"][0]["upstream"]
    assert approval.payload["records"][0]["id"] == "SR-077"
    consent = _consent(source, "SR-077")
    assert upstream["consent_path"] == f"{CONSENT_DIR}/SR-077.json"
    assert upstream["consent_digest"] == "sha256:" + hashlib.sha256(
        consent.read_bytes()).hexdigest()
    assert upstream["requirement_sha256"] == json.loads(
        consent.read_text(encoding="utf-8"))["requirement_sha256"]
    assert upstream["run_id"] == "JEV-REVIEW-INTEGRATION"
    assert upstream["repo_head"] == "0123456789abcdef0123456789abcdef01234567"
    [event] = [e for e in open_core(repo).log_read("events") if e.kind == "import"]
    assert approval.payload["import_event"] == event.digest
    # the approval carries the event it cites, so its re-check needs no log context
    assert approval.payload["import_entry"]["payload"] == dict(event.payload)
    assert event.payload["approved"] == [{"id": r["id"], "hash": r["hash"]}
                                         for r in approval.payload["records"]]


def test_validate_rechecks_by_import(repo: Path, source: Path) -> None:
    from plumb import log
    from plumb.validate import validate

    _consent(source, "SR-078").unlink()
    import_pi_factory(open_core(repo), source)
    core = open_core(repo)
    assert not [f for f in validate(core) if f.code == "approval"]
    approval = _approvals(repo)[0]
    # a by: import approval citing no consent confirms nothing and is a validate error
    forged = dict(approval.payload)
    forged["records"] = [{"id": "SR-078", "hash": core.index()["SR-078"].hash}]
    forged["records"][0]["upstream"] = {
        k: v for k, v in approval.payload["records"][0]["upstream"].items()
        if k != "consent_digest"}
    log.append(core.paths, "events", "approval", forged)
    # and one pinning a hash the import never wrote is an error too
    forged = dict(approval.payload)
    forged["records"] = [{"id": "SR-003", "hash": open_core(repo).index()["SR-003"].hash}]
    forged["records"][0]["upstream"] = dict(approval.payload["records"][0]["upstream"],
                                            consent_path=f"{CONSENT_DIR}/SR-003.json")
    log.append(core.paths, "events", "approval", forged)
    core = open_core(repo)
    errors = [f for f in validate(core) if f.severity == "error" and f.code == "approval"]
    assert {e.subject for e in errors} >= {"SR-078", "SR-003"}
    statuses = core.status(["SR-078", "SR-003", "SR-077"])
    assert statuses["SR-078"].confirmation == "proposed"
    assert statuses["SR-003"].confirmation == "proposed"
    assert statuses["SR-077"].confirmation == "confirmed"


def test_revoked_import_approval_not_written_again(repo: Path, source: Path) -> None:
    from plumb.approvals import revoke

    import_pi_factory(open_core(repo), source)
    revoke(open_core(repo), ["SR-077"])
    assert open_core(repo).status(["SR-077"])["SR-077"].confirmation == "proposed"
    import_pi_factory(open_core(repo), source)
    assert len(_approvals(repo)) == 1
    assert open_core(repo).status(["SR-077"])["SR-077"].confirmation == "proposed"


def test_validate_flags_an_import_event_that_did_not_approve(repo: Path, source: Path) -> None:
    from plumb import log
    from plumb.validate import validate

    import_pi_factory(open_core(repo), source)
    core = open_core(repo)
    approval = _approvals(repo)[0]
    # forging both entries is tamper-evident: validate names the approval
    from plumb.importer.recheck import event_copy

    event = log.append(core.paths, "events", "import", {"approved": []})
    forged = dict(approval.payload, import_event=event.digest, import_entry=event_copy(event))
    log.append(core.paths, "events", "approval", forged)
    errors = [f for f in validate(open_core(repo)) if f.code == "approval"]
    assert any("SR-077" in e.subject and "did not approve" in e.message for e in errors)


# The guarantee (concept 10, R2): a by: import approval confirms only what an import run
# outside the agent session approved after the owner answered its terminal question. One test
# per entry point that writes one: the import API, the import CLI, the core API append, a
# direct log write; and the CLI that reads confirmations.

LOCAL_SR = """---
id: SR-001
title: A local requirement nobody imported
statement: Something the owner never confirmed.
examples:
  - {id: EX-1, given: a state, when: an action, then: a result}
---
"""


def _forged(record_id: str, record_hash: str, cite: str, event=None) -> dict:
    """A well-formed by: import approval with made-up upstream fields, citing ``cite`` and
    carrying a copy of ``event`` when given."""
    from plumb.importer.recheck import event_copy

    return {"records": [{"id": record_id, "hash": record_hash, "upstream": {
        "repo": "pi-agent-factory", "repo_head": "0" * 40,
        "consent_path": f"{CONSENT_DIR}/{record_id}.json", "consent_digest": "sha256:" + "1" * 64,
        "requirement_sha256": "2" * 64, "upstream_hash": "sha256:" + "3" * 64,
        "run_id": "JEV-REVIEW-INTEGRATION"}}],
        "by": "import", "upstream": {}, "import_event": cite,
        "import_entry": event_copy(event) if event is not None else None,
        "prompt_digest": None, "quote": None}


def _approval_errors(repo: Path) -> list[str]:
    from plumb.validate import validate

    return [f.message for f in validate(open_core(repo)) if f.code == "approval"]


def test_import_api_in_agent_session_writes_no_approval(repo: Path, source: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "1")
    report = import_pi_factory(open_core(repo), source)
    assert report["approved"] == [] and _approvals(repo) == []
    assert any(f["kind"] == "approval-withheld" and "SR-077" in f["id"]
               for f in report["findings"])
    statuses = open_core(repo).status(["SR-077", "SR-078"])
    assert {s.confirmation for s in statuses.values()} == {"proposed"}
    # the owner declining at the terminal withholds them too
    from plumb import approvals

    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    monkeypatch.setattr(approvals, "owner_terminal_answer", lambda question: "n")
    report = import_pi_factory(open_core(repo), source)
    assert _approvals(repo) == [] and report["approved"] == []
    # the owner's own run confirms them, without rewriting the records
    monkeypatch.setattr(approvals, "owner_terminal_answer", lambda question: "y")
    report = import_pi_factory(open_core(repo), source)
    assert report["approved"] == ["SR-077", "SR-078"]
    assert open_core(repo).status(["SR-077"])["SR-077"].approved_by == "import"
    assert not _approval_errors(repo)


def test_import_cli_in_agent_session_writes_no_approval(repo: Path, source: Path,
                                                        monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]
                                                        ) -> None:
    from plumb import cli

    monkeypatch.setenv("PLUMB_AGENT_SESSION", "1")
    # a consent the agent made for its own content is no better than a real one here
    assert cli.main(["import", "pi-agent-factory", str(source), "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "0 confirmed by import" in out and "approval-withheld" in out
    assert _approvals(repo) == []
    assert open_core(repo).status(["SR-077"])["SR-077"].confirmation == "proposed"


def test_forged_by_import_through_core_api_confirms_nothing(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    write_record(repo, LOCAL_SR)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "1")
    core = open_core(repo)
    record_hash = core.index()["SR-001"].hash
    # a note, then an approval citing it (case B of the review's repro)
    note = core.log_append("events", "note", {"text": "anything"})
    core.log_append("events", "approval", _forged("SR-001", record_hash, note.digest))
    # an import event approving it, then an approval citing that: still the agent's session
    event = core.log_append("events", "import", {"approved": [{"id": "SR-001",
                                                               "hash": record_hash}]})
    core.log_append("events", "approval", _forged("SR-001", record_hash, event.digest, event))
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation == "proposed" and status.approved_by is None
    errors = _approval_errors(repo)
    assert len(errors) == 2 and all("agent session marker" in e for e in errors)


def test_forged_by_import_through_direct_log_write_confirms_nothing(
        repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import log

    write_record(repo, LOCAL_SR)
    core = open_core(repo)
    record_hash = core.index()["SR-001"].hash
    # outside the marker: the cited entry is not an import event
    note = log.append(core.paths, "events", "note", {"text": "anything"})
    log.append(core.paths, "events", "approval", _forged("SR-001", record_hash, note.digest))
    # an import event written in the agent session backs no approval
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "1")
    event = log.append(core.paths, "events", "import",
                       {"approved": [{"id": "SR-001", "hash": record_hash}]})
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    log.append(core.paths, "events", "approval",
               _forged("SR-001", record_hash, event.digest, event))
    # an import event that approved another hash backs no approval of this one
    event = log.append(core.paths, "events", "import",
                       {"approved": [{"id": "SR-001", "hash": "sha256:" + "4" * 64}]})
    log.append(core.paths, "events", "approval",
               _forged("SR-001", record_hash, event.digest, event))
    # a copy that is not the cited event (its approval list widened) backs nothing either
    event = log.append(core.paths, "events", "import", {"approved": []})
    widened = _forged("SR-001", record_hash, event.digest, event)
    widened["import_entry"]["payload"] = {"approved": [{"id": "SR-001", "hash": record_hash}]}
    log.append(core.paths, "events", "approval", widened)
    assert open_core(repo).status(["SR-001"])["SR-001"].confirmation == "proposed"
    errors = _approval_errors(repo)
    assert sum("carries no copy of the import event" in e for e in errors) == 2
    assert sum("import event written under the agent session marker" in e
               for e in errors) == 1
    assert sum("did not approve" in e for e in errors) == 1


def test_forged_by_import_is_proposed_through_the_cli(repo: Path, write_record,
                                                      monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]
                                                      ) -> None:
    from plumb import cli

    write_record(repo, LOCAL_SR)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "1")
    core = open_core(repo)
    note = core.log_append("events", "note", {"text": "anything"})
    core.log_append("events", "approval",
                    _forged("SR-001", core.index()["SR-001"].hash, note.digest))
    capsys.readouterr()
    assert cli.main(["status", "--json", "--root", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["requirements"]["confirmed"] == 0 and "SR-001" in data["awaiting"]
    assert cli.main(["validate", "--root", str(repo)]) != 0
    assert "agent session marker" in capsys.readouterr().out


def test_hand_written_approval_with_a_made_up_event_is_flagged(repo: Path, write_record) -> None:
    """A raw log line carrying an import event that was never written: confirm's
    self-contained re-check cannot see the log, so validate names it (and the broken chain);
    tamper-evident, as concept 4.6 states."""
    from plumb.log import entry_digest
    from plumb.normalize import canonical_json

    write_record(repo, LOCAL_SR)
    core = open_core(repo)
    record_hash = core.index()["SR-001"].hash
    made_up = {"at": "2026-10-06T00:00:00Z", "marker": "none", "prev": None,
               "payload": {"approved": [{"id": "SR-001", "hash": record_hash}]}}
    cited = entry_digest({"v": 1, "kind": "import", **made_up})
    payload = _forged("SR-001", record_hash, cited)
    payload["import_entry"] = made_up
    line = {"v": 1, "kind": "approval", "at": "2026-10-06T00:00:01Z", "marker": "none",
            "payload": payload, "prev": cited}
    line["digest"] = entry_digest(line)
    path = core.paths.log_path("events")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_json(line) + b"\n")
    errors = _approval_errors(repo)
    assert any("not the log entry right before it" in e for e in errors)
    from plumb.validate import validate

    assert any(f.code == "log" for f in validate(open_core(repo)))


# One choke point, two lanes (review HIGH, next-plan 3.1): confirm.checked_entries re-checks
# every approval source. IMPORT's by: import re-check needs no log context, so CAPTURE's
# auto-jev re-check there merges without a conflict; this test runs through whichever
# checked_entries the branch has, before and after that merge.

def test_checked_entries_rechecks_import_and_auto_jev_approvals(
        repo: Path, source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb import approvals
    from plumb.confirm import checked_entries

    monkeypatch.setattr(approvals, "owner_terminal_answer", lambda question: "y")
    report = import_pi_factory(open_core(repo), source)
    assert report["approved"] == ["SR-077", "SR-078"]
    core = open_core(repo)
    # an auto-jev approval with no owner config event and no calibration: it fails closed
    sr003 = core.index()["SR-003"].hash
    from understand.fakes import as_worker

    with as_worker(repo, "s1"):      # only the worker writes an auto-jev approval (SR-210)
        core.log_append("events", "approval", {
            "records": [{"id": "SR-003", "hash": sr003}], "by": "auto-jev", "score": 0.99,
            "confidence": "high", "prompt_digest": "sha256:" + "5" * 64,
            "backend_version": "jev-test", "quote": None})
    core = open_core(repo)
    checked = {str(e.payload.get("by")): problem
               for e, problem in checked_entries(core.events(),
                                                 core.config.approve.affirmations)}
    assert checked["import"] is None
    assert checked["auto-jev"] is not None
    statuses = core.status(["SR-077", "SR-078", "SR-003"])
    assert statuses["SR-077"].approved_by == "import"
    assert statuses["SR-078"].confirmation == "confirmed"
    assert statuses["SR-003"].confirmation == "proposed"
