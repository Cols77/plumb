"""I5: ``by: import`` approvals only from upstream human consent pinning the current content
(next-plan 9.3, concept 10, R2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from importer_helpers import CONSENT_DIR, make_source, rewrite, write

from plumb.api import open_core
from plumb.importer.pi_factory import import_pi_factory

pytestmark = pytest.mark.sr("SR-059")


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
    event = log.append(core.paths, "events", "import", {"approved": []})
    forged = dict(approval.payload, import_event=event.digest)
    log.append(core.paths, "events", "approval", forged)
    errors = [f for f in validate(open_core(repo)) if f.code == "approval"]
    assert any(e.subject == "SR-077" and "did not approve" in e.message for e in errors)
