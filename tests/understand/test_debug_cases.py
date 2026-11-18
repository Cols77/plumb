"""SR-300: the debug cases a landing writes reach the agent as text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.understand import summary

pytestmark = pytest.mark.sr("SR-300")

CASES = [{"id": f"c{n}", "kind": "stale-link", "target": f"SR-{n}", "detail": "d",
          "state": "open"} for n in (1, 2, 3)]


def test_ex1_three_cases_are_told_with_the_workflow_on_sonnet(repo: Path) -> None:
    summary.write_cases(open_core(repo), "abc123", CASES)
    path = repo / ".iaso" / "cache" / "debug" / "abc123.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == ["c1", "c2", "c3"]
    assert set(rows[0]) == {"id", "kind", "target", "detail", "state"}
    text = summary.cases_text(rows)
    assert "3 debug cases" in text and "Workflow on Sonnet" in text and "?" not in text
    # INT-114 (DEC-384): a changed meaning is one question through the question tool, no card
    assert "card" not in text.lower() and "question tool" in text


def test_ex4_no_cases_write_nothing(repo: Path) -> None:
    summary.write_cases(open_core(repo), "abc123", [])
    assert not (repo / ".iaso" / "cache" / "debug").exists()


def test_ex2_a_resolved_case_is_counted_and_no_longer_told(repo: Path) -> None:
    """SR-300 EX-2: the debug workflow repins one stale link and marks its case done: the
    next text counts it resolved and lists the two still open."""
    from iaso.boundary import landing

    summary.write_cases(open_core(repo), "abc123", CASES)
    assert summary.resolve_cases(repo, ["c2"]) == 1
    ((key, text),) = landing.lines(repo)
    assert "2 debug cases open, 1 resolved" in text and "c2" not in text and key == "cases:2:1"
    assert summary.resolve_cases(repo, ["c1", "c3"]) == 2
    assert landing.lines(repo) == []


def test_a_case_repeated_by_later_landings_counts_once(repo: Path) -> None:
    """Every landing writes its own file and repeats the cases still open: one case, once."""
    from iaso.boundary import landing

    summary.write_cases(open_core(repo), "abc123", CASES)
    summary.write_cases(open_core(repo), "def456", CASES[:2])
    ((key, text),) = landing.lines(repo)
    assert key == "cases:3:0" and text.startswith("iaso: 3 debug cases open")


def test_a_long_list_names_twenty_and_counts_the_rest(repo: Path, capsys, monkeypatch) -> None:
    many = [{"id": f"c{n}", "kind": "unrun-test" if n % 2 else "stale-link", "target": f"t{n}",
             "detail": "d", "state": "open"} for n in range(500)]
    text = summary.cases_text(many, workflow="debug-cases")
    assert "500 debug cases open" in text and len(text) < 4000
    assert "- c19 " in text and "- c20 " not in text and "c20," not in text
    assert "480 more (240 stale-link, 240 unrun-test)" in text
    assert "iaso understand debug list" in text
    summary.write_cases(open_core(repo), "abc123", many)
    monkeypatch.chdir(repo)
    assert summary.run_debug(["list"]) == 0
    out = capsys.readouterr().out
    assert "- c499 (unrun-test) t499: d" in out and "500 open, 0 resolved" in out
