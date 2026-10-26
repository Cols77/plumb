"""SR-233: a record a newer record supersedes is retired: it counts in no status and is
rated by no triage."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.commands import status_data

pytestmark = pytest.mark.sr("SR-233")

OLD = """---
id: SR-001
title: add adds
feature: FEAT-001
statement: add(a, b) returns the sum.
---
"""
NEW = """---
id: SR-002
title: add adds, one behaviour
feature: FEAT-001
statement: add(a, b) returns the sum of a and b.
links:
- kind: supersedes
  to: SR-001
---
"""


def test_a_retired_requirement_counts_nowhere(repo: Path, write_record) -> None:
    write_record(repo, OLD)
    write_record(repo, NEW)
    data = status_data(open_core(repo))
    assert data["records"]["requirement"] == 1
    assert data["awaiting"] == ["SR-002"] and "SR-001" not in data["failing"]


@pytest.mark.sr("SR-289")
def test_ex1_a_supersedes_link_to_a_deleted_record_is_not_dangling(repo: Path,
                                                                   write_record) -> None:
    """SR-289 EX-1 (DEC-145): the replaced record's file is gone; the supersedes link stands,
    counts as retired, and validate reports no dangling link for it."""
    from plumb.links import link_states
    from plumb.validate import validate

    write_record(repo, OLD)
    write_record(repo, NEW)
    (repo / ".plumb" / "requirements" / "SR-001.md").unlink()
    core = open_core(repo)
    [state] = link_states(core, ["SR-002"])
    assert state.state == "retired"
    assert not [f for f in validate(core) if f.code == "dangling"]
    assert status_data(core)["records"]["requirement"] == 1


@pytest.mark.sr("SR-289")
def test_ex7_a_failing_approval_of_a_gone_record_is_not_reported(repo: Path,
                                                                 write_record) -> None:
    """SR-289 EX-7 (DEC-145): a button approval of SR-001, which left the tree, fails its
    re-check (no drawn offer) but validate does not report it."""
    from plumb.validate import validate

    write_record(repo, NEW)
    core = open_core(repo)
    core.log_append("events", "approval", {"by": "owner", "via": "button", "records": [
        {"id": "SR-001", "hash": "sha256:0"}]})
    assert not [f for f in validate(open_core(repo)) if f.code == "approval"]


@pytest.mark.sr("SR-289")
def test_ex5_a_card_about_a_gone_record_is_moot(repo: Path, write_record) -> None:
    """SR-289 EX-5: a decision card whose record left the tree is neither shown nor counted."""
    from plumb.contracts import CardState, ClarifyQuestion
    from plumb.understand import summary

    write_record(repo, NEW)
    core = open_core(repo)
    card = CardState(id="c1", kind="decision", topic="old", questions=(
        ClarifyQuestion(id="q1", text="keep it?", record="DEC-001"),))
    assert summary._moot(core, card, core.status(), set()) is None
    # an intent conflict card on a record the clean-up deleted (IC-002 on SR-103)
    conflict = CardState(id="conflict:IC-002", kind="conflict", topic="old", questions=(
        ClarifyQuestion(id="q1", text="which version?", record="SR-001"),))
    assert summary._moot(core, conflict, core.status(), set()) is None
    kept = CardState(id="conflict:IC-003", kind="conflict", topic="live", questions=(
        ClarifyQuestion(id="q1", text="which version?", record="SR-002"),))
    assert summary._moot(core, kept, core.status(), set()) is kept
