"""open_core satisfies the frozen CoreAPI protocol (spec 12.1, 12.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.contracts import CoreAPI


@pytest.mark.sr("SR-230")
def test_open_core_is_a_core_api(repo: Path) -> None:
    core = open_core(repo)
    assert isinstance(core, CoreAPI)
    assert core.root == repo
    record = core.write_record("intent", {"title": "Grounded", "quote": "ok"})
    assert record.id == "INT-001" and core.index()["INT-001"].hash == record.hash
    assert core.records_for_paths([record.path]) == {record.path: ("INT-001",)}
    entry = core.log_append("events", "repin", {"links": []})
    assert [e.digest for e in core.log_read("events")] == [entry.digest]
