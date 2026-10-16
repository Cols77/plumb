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
    assert data["awaiting"] == ["SR-002"]


def test_triage_rates_no_retired_record(repo: Path, write_record) -> None:
    from plumb.capture.triage import triage

    write_record(repo, OLD)
    write_record(repo, NEW)
    view = triage(open_core(repo), backend=None)
    assert [i.id for i in view.individual] == ["SR-002"]
