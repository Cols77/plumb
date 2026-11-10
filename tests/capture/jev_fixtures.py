"""A repository calibrated against the JEV stub (sp2 8.2, 8.3): the owner's own decisions
per record kind, and the stub's answers keyed on what the claim says."""

from __future__ import annotations

from pathlib import Path

from capture_helpers import JevStub, record_text, use_jev

from iaso.api import open_core

LOW_MARKERS = ("won't:", "not:", "not true", "UNFAITHFUL")


def claim_of(state: str) -> str:
    return state.split("Claim (", 1)[1] if "Claim (" in state else state


def default_noul(state: str) -> float:
    claim = claim_of(state)
    if "HALF-FAITHFUL" in claim:
        return 0.6
    if any(marker in claim for marker in LOW_MARKERS):
        return 0.2
    return 0.95


def owner_decisions(repo: Path, write_record, *, intents: int = 20, revoked: int = 3,
                    requirements: int = 0, revoked_requirements: int = 0) -> None:
    """``intents`` INT read-backs and ``requirements`` SRs the owner confirmed, and
    ``revoked`` / ``revoked_requirements`` the owner confirmed then revoked."""
    from iaso.approvals import approve, revoke

    for n in range(intents + revoked):
        bad = n >= intents
        name = f"alpha{chr(97 + n % 26)}"
        write_record(repo, record_text(
            f"INT-{100 + n}", f"owner wish {n}", quote=f"please build feature {name}",
            readback=("UNFAITHFUL rewrite " if bad else "") + f"build feature {name}",
            will=[f"feature {name}"]))
    write_record(repo, record_text("INT-099", "requirement words",
                                   quote="totals are shown on the invoice page",
                                   readback="totals are shown on the invoice page"))
    for n in range(requirements + revoked_requirements):
        bad = n >= requirements
        write_record(repo, record_text(
            f"SR-{100 + n}", f"invoice rule {n}",
            statement=("UNFAITHFUL " if bad else "") + "totals are shown on the invoice page",
            examples=[{"id": "EX-1", "given": "an invoice", "when": "the page opens",
                       "then": "totals are shown", "quote": "totals are shown"}],
            links=[{"kind": "derives_from", "to": "INT-099"}]))
    ids = [f"INT-{100 + n}" for n in range(intents + revoked)]
    ids += [f"SR-{100 + n}" for n in range(requirements + revoked_requirements)]
    approve(open_core(repo), ids)
    bad_ids = [f"INT-{100 + n}" for n in range(intents, intents + revoked)]
    bad_ids += [f"SR-{100 + n}"
                for n in range(requirements, requirements + revoked_requirements)]
    if bad_ids:
        revoke(open_core(repo), bad_ids)


def calibrated(repo: Path, write_record, monkeypatch, *, requirements: bool = False,
               noul=None) -> JevStub:
    """A repository with JEV configured against a stub and a passing calibration (the
    intent read-back kind; the requirement kind too with ``requirements``)."""
    from iaso.capture.calibrate import calibrate

    stub = JevStub(noul or default_noul)
    use_jev(repo, stub, monkeypatch)
    owner_decisions(repo, write_record, requirements=20 if requirements else 0,
                    revoked_requirements=3 if requirements else 0)
    entry, results = calibrate(open_core(repo))
    assert results["intent-readback"].passing, results["intent-readback"].reasons
    if requirements:
        assert results["example-restatement"].passing, results["example-restatement"].reasons
    return stub
