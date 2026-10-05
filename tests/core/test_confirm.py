"""K5: derived confirmation states (spec 5.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb import approvals
from plumb.api import open_core
from plumb.contracts import Target

pytestmark = pytest.mark.sr("SR-004")

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
