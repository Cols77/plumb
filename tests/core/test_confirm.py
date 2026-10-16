"""K5: derived confirmation states (spec 5.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb import approvals
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-206")

SR = """---
id: SR-001
title: Links pin both ends
statement: Both ends are pinned.
examples:
  - {id: EX-1, given: g, when: w, then: t}
  - {id: EX-2, given: g2, when: w2, then: t2}
---
"""


@pytest.fixture
def setup(repo: Path, write_record) -> Path:
    write_record(repo, SR)
    return repo


def _confirmation(root: Path, record_id: str = "SR-001") -> str:
    return open_core(root).status([record_id])[record_id].confirmation


def _edit(root: Path) -> None:
    path = root / ".plumb" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Both ends", "Each end"),
                    encoding="utf-8")


def test_proposed_until_approved(setup: Path) -> None:
    assert _confirmation(setup) == "proposed"
    status = open_core(setup).status()["SR-001"]
    assert status.approved_by is None and status.covered is False


def test_approval_event_at_current_hash_confirms(setup: Path) -> None:
    approvals.approve(open_core(setup), ["SR-001"])
    status = open_core(setup).status()["SR-001"]
    assert status.confirmation == "confirmed"
    assert status.approved_by == "owner"


def test_edit_after_approval_is_unconfirmed_edit(setup: Path) -> None:
    approvals.approve(open_core(setup), ["SR-001"])
    _edit(setup)
    assert _confirmation(setup) == "unconfirmed-edit"
    approvals.approve(open_core(setup), ["SR-001"])
    assert _confirmation(setup) == "confirmed"


def test_revocation_returns_to_proposed(setup: Path) -> None:
    approvals.approve(open_core(setup), ["SR-001"])
    approvals.revoke(open_core(setup), ["SR-001"])
    assert _confirmation(setup) == "proposed"
    # revoking the newer approval returns to the older one: an unconfirmed edit
    approvals.approve(open_core(setup), ["SR-001"])
    _edit(setup)
    approvals.approve(open_core(setup), ["SR-001"])
    approvals.revoke(open_core(setup), ["SR-001"])
    assert _confirmation(setup) == "unconfirmed-edit"


def test_covered_requires_verified_by_per_example(setup: Path) -> None:
    (setup / "tests").mkdir()
    (setup / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    core = open_core(setup)
    core.add_link("SR-001", "verified_by", Target(path="tests/test_a.py"), example="EX-1")
    approvals.approve(open_core(setup), ["SR-001"])
    status = open_core(setup).status()["SR-001"]
    assert status.confirmation == "confirmed"
    assert status.uncovered_examples == ("EX-2",) and status.covered is False
    open_core(setup).add_link("SR-001", "verified_by", Target(path="tests/test_a.py"),
                              example="EX-2")
    status = open_core(setup).status()["SR-001"]
    assert status.uncovered_examples == () and status.covered is True


def _drawn_offer(root: Path) -> tuple[object, str, str]:
    """The panel registered for session s1 and a trial card on SR-001 drawn: the core,
    the offer and the key digest (``plumb.mod``)."""
    import hashlib

    from plumb.mod import offers, session
    from plumb.understand import cardstore, trial

    core = open_core(root)
    cardstore.save(root, "s1", [trial.card(core, trial.Candidate(core.index()["SR-001"], 0.9, {}))])
    digest = hashlib.sha256(bytes.fromhex("a1" * 32)).hexdigest()
    session.hello(core, "s1", digest)
    (card,) = offers.drawn_cards(core, "s1", digest)
    return core, card["offers"][0]["offer_id"], digest


def _button(core, offer: str, digest: str, record_hash: str):
    card = f"trial:SR-001@{record_hash.split(':')[-1][:12]}"
    return core.log_append("events", "approval", {
        "by": "owner", "via": "button", "session": "s1", "offer": offer, "key_digest": digest,
        "card": card, "question": f"{card}#1",
        "records": [{"id": "SR-001", "hash": record_hash}]})


@pytest.mark.sr("SR-086")
def test_button_approval_confirms_only_at_a_drawn_offer(setup: Path) -> None:
    """SR-086 EX-1, EX-9: an owner button approval naming the offer drawn for this record at
    this version confirms; the same entry naming no drawn offer confirms nothing."""
    from plumb import confirm

    core, offer, digest = _drawn_offer(setup)
    forged = _button(core, "sha256:" + "0" * 64, digest, core.index()["SR-001"].hash)
    assert "offer was not drawn" in confirm.entry_problem(forged, set(), (), core)
    assert _confirmation(setup) == "proposed"
    pressed = _button(core, offer, digest, core.index()["SR-001"].hash)
    assert confirm.entry_problem(pressed, set(), (), open_core(setup)) is None
    assert _confirmation(setup) == "confirmed"
    assert open_core(setup).status()["SR-001"].approved_by == "owner"
    _edit(setup)                                   # the confirmed version is the drawn one
    assert _confirmation(setup) == "unconfirmed-edit"


@pytest.mark.sr("SR-209")
def test_button_approval_under_the_marker_or_with_another_key_confirms_nothing(
        setup: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SR-112 EX-7: a button approval the agent writes (under its marker, or without the
    panel's key) is not accepted."""
    from plumb import confirm

    core, offer, digest = _drawn_offer(setup)
    record_hash = core.index()["SR-001"].hash
    other = _button(core, offer, "f" * 64, record_hash)
    assert "key" in confirm.entry_problem(other, set(), (), core)
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    marked = _button(core, offer, digest, record_hash)
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert "marker" in confirm.entry_problem(marked, set(), (), core)
    assert _confirmation(setup) == "proposed"
