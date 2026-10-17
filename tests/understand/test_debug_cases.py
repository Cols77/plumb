"""SR-300: the debug cases a landing writes reach the agent as text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.understand import summary

pytestmark = pytest.mark.sr("SR-300")

CASES = [{"id": f"c{n}", "kind": "stale-link", "target": f"SR-{n}", "detail": "d",
          "state": "open"} for n in (1, 2, 3)]


def test_ex1_three_cases_are_told_with_the_workflow_on_sonnet(repo: Path) -> None:
    summary.write_cases(open_core(repo), "abc123", CASES)
    path = repo / ".plumb" / "cache" / "debug" / "abc123.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == ["c1", "c2", "c3"]
    assert set(rows[0]) == {"id", "kind", "target", "detail", "state"}
    text = summary.cases_text(rows)
    assert "3 debug cases" in text and "Workflow on Sonnet" in text and "?" not in text


def test_ex4_no_cases_write_nothing(repo: Path) -> None:
    summary.write_cases(open_core(repo), "abc123", [])
    assert not (repo / ".plumb" / "cache" / "debug").exists()
