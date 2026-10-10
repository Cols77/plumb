"""M2: the glance of approvals made in the range, repinned requirements without a fidelity
judgment, and the advisory fidelity list (sp3 3.1, 3.2, 6; R2, R4, R8 B, R13 Q4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from logutil import legacy_relay
from merge_helpers import INT, SR2, commit, repin_all, write

from plumb import approvals
from plumb.api import open_core
from plumb.boundary import merge_report, render
from plumb.contracts import Judgment, Target

SR1 = "---\nid: SR-001\ntitle: Links pin both ends\nstatement: Both ends are pinned.\n---\n"


@pytest.fixture
def base(repo: Path) -> tuple[Path, str]:
    write(repo, ".plumb/intents/INT-001.md", INT)
    write(repo, ".plumb/requirements/SR-001.md", SR1)
    write(repo, ".plumb/requirements/SR-002.md", SR2)
    write(repo, "src/mod.py", "x = 1\n")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo, commit(repo, "base")


def _prompt(root: Path, text: str, **extra: object) -> str:
    digest = approvals.prompt_digest(text)
    path = root / ".plumb" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        # logged as the host's prompt hook logs it (R13 Q4), unless the test says otherwise
        line = {"digest": digest, "session": "s", "at": "t", "text": text,
                **({} if extra else {"via": "hook"})}
        handle.write(json.dumps({**line, **extra}) + "\n")
    return digest


def _glance_text(report) -> str:
    lines = render(report)
    start = next(i for i, line in enumerate(lines) if line.startswith("approvals in range"))
    return "\n".join(lines[start:])


@pytest.mark.sr("SR-047")
def test_lists_agent_relayed_with_quote(base) -> None:
    root, sha = base
    digest = _prompt(root, "SR-002 looks good, approved")
    legacy_relay(root, ["SR-002"], digest, "SR-002 looks good, approved")
    approvals.approve(open_core(root), ["INT-001"])
    report = merge_report(open_core(root), sha, run_full=False)
    groups = [row["by"] for row in report.glance]
    assert groups == ["agent-relayed", "owner"]  # agent-relayed first, for the glance
    relayed = report.glance[0]
    assert relayed["quote"] == "SR-002 looks good, approved"
    assert relayed["prompt_digest"] == digest
    assert relayed["revoke"] == "plumb revoke SR-002"
    assert relayed["self_recorded"] is False
    text = _glance_text(report)
    assert 'AGENT-RELAYED SR-002 quote "SR-002 looks good, approved"' in text
    assert digest[:19] in text and "plumb revoke SR-002" in text
    assert "owner INT-001" in text


@pytest.mark.sr("SR-047")
def test_lists_auto_jev_with_score(base) -> None:
    """SR-047 EX-2: an auto-jev approval shows its score, model version and revoke form."""
    root, sha = base
    core = open_core(root)
    record = core.index()["INT-001"]
    core.log_append("events", "approval", {
        "records": [{"id": "INT-001", "hash": record.hash}], "by": "auto-jev",
        "score": 0.96, "confidence": "high", "prompt_digest": "sha256:" + "a" * 64,
        "backend": "jev", "model_version": "jev-2026-09", "claim_kind": "intent"})
    report = merge_report(open_core(root), sha, run_full=False)
    row = report.glance[0]
    assert row["by"] == "auto-jev" and row["score"] == 0.96
    assert row["model_version"] == "jev-2026-09" and row["revoke"] == "plumb revoke INT-001"
    text = _glance_text(report)
    assert "AUTO-JEV INT-001 score 0.96 (high) model jev-2026-09" in text
    assert "plumb revoke INT-001" in text


@pytest.mark.sr("SR-047")
def test_lists_capture_written_auto_jev(base) -> None:
    """Cross-lane: the payload exactly as CAPTURE's writer (``capture.autoapprove.gate``)
    records it, the fields nested under ``auto`` with the label in ``confidence_label``,
    shows its score, confidence label and model version (R8 B)."""
    root, sha = base
    core = open_core(root)
    record = core.index()["INT-001"]
    core.log_append("events", "approval", {
        "records": [{"id": "INT-001", "hash": record.hash}], "by": "auto-jev",
        "prompt_digest": "sha256:" + "b" * 64, "quote": None, "quote_digest": None,
        "auto": {"score": 0.97, "confidence": 0.91, "confidence_label": "high",
                 "backend": "jev:jev-1.13.0", "model_version": "jev-1.13.0",
                 "calibration": "sha256:" + "c" * 64, "claim_kind": "intent-readback",
                 "threshold": 0.9, "prompt_via": "hook", "min_probability": 0.9,
                 "min_confidence": "high", "parts": 1, "fingerprints": ["f"]}})
    report = merge_report(open_core(root), sha, run_full=False)
    row = report.glance[0]
    assert (row["score"], row["confidence"], row["model_version"]) == (0.97, "high",
                                                                       "jev-1.13.0")
    assert row["backend"] == "jev:jev-1.13.0" and row["claim_kind"] == "intent-readback"
    assert "AUTO-JEV INT-001 score 0.97 (high) model jev-1.13.0" in _glance_text(report)


@pytest.mark.sr("SR-047")
def test_self_recorded_message_labelled(base) -> None:
    """R13 Q4: a relay resting on a message the agent recorded itself (a host without a
    prompt hook) is labelled "self-recorded message"."""
    root, sha = base
    digest = _prompt(root, "ok SR-002", self_recorded=True, host="cli")
    legacy_relay(root, ["SR-002"], digest, "ok SR-002", self_recorded=True)
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.glance[0]["self_recorded"] is True
    assert "self-recorded message" in _glance_text(report)


@pytest.mark.sr("SR-047")
def test_revocations_and_import_listed_without_revoke_form(base) -> None:
    root, sha = base
    approvals.approve(open_core(root), ["SR-002"])
    approvals.revoke(open_core(root), ["SR-002"])
    report = merge_report(open_core(root), sha, run_full=False)
    kinds = [(row["kind"], row["by"]) for row in report.glance]
    assert kinds == [("approval", "owner"), ("revocation", "owner")]
    assert report.glance[1]["revoke"] is None


@pytest.mark.sr("SR-050")
def test_repinned_unjudged_listed_not_held(base) -> None:
    """A confirmed requirement whose implementing end changed and was repinned with no
    fidelity judgment is a glance item, not a wait."""
    root, _ = base
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    sha = commit(root, "confirmed")
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.repinned_unjudged == ("SR-001",)
    assert report.exit == 0, render(report)
    assert any("repinned without a judgment: SR-001" in line for line in render(report))


@pytest.mark.sr("SR-050")
def test_fidelity_never_changes_exit(base) -> None:
    """SR-050 EX-1 and EX-2: unjudged and drifts are listed; the exit stays the rest's."""
    root, _ = base
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    sha = commit(root, "confirmed")
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    report = merge_report(open_core(root), sha, run_full=False)
    assert [(f["id"], f["state"]) for f in report.fidelity] == [("SR-001", "unjudged")]
    assert "plumb fidelity SR-001" in "\n".join(render(report))
    assert report.exit == 0
    from plumb.judgment.fidelity import judge

    judge(open_core(root), "SR-001", "drifts", "the code ignores an example")
    report = merge_report(open_core(root), sha, run_full=False)
    assert [(f["id"], f["state"]) for f in report.fidelity] == [("SR-001", "drifts")]
    assert report.repinned_unjudged == ()
    assert report.exit == 0


class _FakeJev:
    name = "jev"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fidelity(self, packet):
        self.calls.append(packet.requirement)
        return Judgment(action="fidelity", subject=packet.requirement, verdict="fits",
                        confidence=0.93, tier="accept", backend="jev:test-1",
                        fingerprint=packet.fingerprint)


@pytest.mark.sr("SR-050")
def test_jev_prescores_fidelity_without_recording(base, monkeypatch) -> None:
    """MS1: with JEV configured, up to five packets are scored and shown; nothing is logged
    as the host agent's judgment and the exit is unchanged."""
    root, _ = base
    approvals.approve(open_core(root), ["SR-001", "INT-001"])
    write(root, ".plumb/config.yaml", "judgment:\n  backend: jev\n")
    sha = commit(root, "confirmed")
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    fake = _FakeJev()
    import plumb.judgment

    monkeypatch.setattr(plumb.judgment, "get_backend", lambda core, hook: fake)
    before = len(open_core(root).events())
    report = merge_report(open_core(root), sha, run_full=False)
    assert fake.calls == ["SR-001"]
    assert report.fidelity[0]["jev"] == {"verdict": "fits", "confidence": 0.93,
                                         "backend": "jev:test-1"}
    assert "jev: fits (0.93)" in "\n".join(render(report))
    assert len(open_core(root).events()) == before
    assert report.exit == 0
