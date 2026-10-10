"""SP8 3.2 item 6: a settled approval counts as confirmed everywhere and is listed apart as
"settled from your words". With the phase C stub, a hand-written settled entry confirms
nothing; with the recheck patched to accept, it confirms."""

from __future__ import annotations

from pathlib import Path

import pytest
from understand.fakes import as_worker

from plumb.api import open_core
from plumb.present import owner_text

pytestmark = pytest.mark.sr("SR-105")

SR = ("---\nid: SR-001\ntitle: Add multiply\nfeature: FEAT-001\nstatement: multiply two numbers\n"
      "examples:\n- id: EX-1\n  given: 2 and 3\n  when: multiplied\n  then: 6\n---\n")


@pytest.fixture
def core(repo: Path, write_record):
    write_record(repo, SR)
    return open_core(repo)


def _settle(core, record_id: str = "SR-001") -> None:
    item = {"id": record_id, "hash": core.index()[record_id].hash}
    with as_worker(core.root, "s1"):
        core.log_append("events", "approval", {
            "by": "settled", "session": "s1", "records": [item], "job": "judge-0",
            "model": "fake", "score": 0.97, "premise_digest": "sha256:0",
            "calibration": "sha256:1"})


def test_stub_recheck_accepts_nothing(core) -> None:
    _settle(core)
    fresh = open_core(core.root)
    status = fresh.status(["SR-001"])["SR-001"]
    assert status.confirmation == "proposed"
    assert status.settled is False


def test_settled_counts_as_confirmed(core, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.understand import recheck_settled

    monkeypatch.setattr(recheck_settled, "problem", lambda entry, core: None)
    _settle(core)
    fresh = open_core(core.root)
    status = fresh.status(["SR-001"])["SR-001"]
    assert status.confirmation == "confirmed"
    assert status.approved_by == "settled"
    assert status.settled is True


def test_settled_is_listed_apart(core, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.hosts.claude_code.snapshot import build_snapshot
    from plumb.present.render import status_card

    from plumb.understand import recheck_settled

    monkeypatch.setattr(recheck_settled, "problem", lambda entry, core: None)
    _settle(core)
    fresh = open_core(core.root)
    snapshot = build_snapshot(fresh)
    assert snapshot.requirements_confirmed == 1
    assert snapshot.confirmed_by.get("settled") == 1
    assert owner_text.SETTLED_COUNT.format(n=1) in status_card(snapshot)


def test_glance_and_validate_accept_a_rechecked_settled_entry(
        core, monkeypatch: pytest.MonkeyPatch) -> None:
    from plumb.boundary.glance import glance_line, glance_rows
    from plumb.understand import recheck_settled
    from plumb.validate import validate

    monkeypatch.setattr(recheck_settled, "problem", lambda entry, core: None)
    _settle(core)
    fresh = open_core(core.root)
    rows = glance_rows(fresh, [])
    line = glance_line([r for r in rows if r["by"] == "settled"][0])
    assert owner_text.SETTLED_GLANCE in line
    assert not [f for f in validate(fresh) if f.severity == "error"
                and "settled" in f.message]


def test_validate_reports_a_hand_written_settled_entry(core) -> None:
    from plumb.validate import validate

    _settle(core)
    errors = [f for f in validate(open_core(core.root)) if f.severity == "error"]
    assert any(owner_text.NOT_AVAILABLE in f.message for f in errors)
