"""SR-367: the known problems pane's data. ``plumb mod known`` answers how many known problems
are open and each one's symptom, cause, fix, state and case history, open ones first; an issue
whose case reopened counts open. The session start's lines for the agent stay as they are."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mod.helpers import run_mod

from plumb import debug

pytestmark = pytest.mark.sr("SR-367")


def _issue(n: int, state: str = "fixed") -> dict:
    return {"id": f"KI-{n}", "title": f"problem {n}", "symptom": f"symptom {n}",
            "cause": f"cause {n}", "fix": f"abc{n}", "state": state, "fixed": "2026-10-20"}


@pytest.fixture
def register(repo: Path) -> Path:
    """Two known problems open (KI-1 open, KI-3 fixed but its case reopened), five fixed."""
    issues = [_issue(1, "open"), *(_issue(n) for n in range(2, 8))]
    (repo / ".plumb" / "known-issues.json").write_text(json.dumps({"issues": issues}), "utf-8")
    case = {"id": "KI-3", "state": "open", "detail": "symptom 3 again",
            "history": [{"state": "fixed", "landed": "abc3"}]}
    folder = repo.joinpath(*debug.STORE)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "KI-3.json").write_text(json.dumps(case), "utf-8")
    return repo


def test_ex1_two_open_counted_open_ones_first(register: Path) -> None:
    pane = debug.known_pane(register)
    assert pane["open"] == 2
    assert [r["id"] for r in pane["issues"][:2]] == ["KI-1", "KI-3"]
    assert [r["state"] for r in pane["issues"]] == ["open", "open", *["fixed"] * 5]


def test_ex2_each_problem_has_symptom_cause_fix_state_and_history(register: Path) -> None:
    three = next(r for r in debug.known_pane(register)["issues"] if r["id"] == "KI-3")
    assert three == {"id": "KI-3", "title": "problem 3", "symptom": "symptom 3",
                     "cause": "cause 3", "fix": "abc3", "state": "open", "fixed": "2026-10-20",
                     "history": ["fixed, fix abc3", "open again: symptom 3 again"]}


def test_ex3_none_open_counts_zero(repo: Path) -> None:
    (repo / ".plumb" / "known-issues.json").write_text(
        json.dumps({"issues": [_issue(2)]}), "utf-8")
    assert debug.known_pane(repo)["open"] == 0
    assert debug.known_pane(repo / "nowhere") == {"open": 0, "issues": []}


def test_the_mod_command_answers_the_pane(register: Path, monkeypatch, capsys) -> None:
    code, answer, _ = run_mod(monkeypatch, capsys, register, "known", stdin={})
    assert code == 0 and answer == debug.known_pane(register)


def test_the_session_start_lines_are_unchanged(register: Path) -> None:
    assert debug.known_lines(register)[0] == ("plumb: known issues open: KI-1 problem 1; "
                                              "KI-3 problem 3")
