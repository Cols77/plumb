"""SR-175: drift is checked for coverage before any card (DEC-061). The end-of-turn step runs
the linked tests and the meaning check, repins with a note and files a card only when the
requirement should change fundamentally; tests and models are stubbed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.stale_asked import asked
from plumb import links, stale
from plumb.api import open_core
from plumb.contracts import Target
from plumb.understand import repin

pytestmark = pytest.mark.sr("SR-198")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CODE = "def add(a, b):\n    return a + b\n"
REFACTORED = "def add(a, b):\n    return b + a\n"
LINK = "SR-001#0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py", symbol="add"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    monkeypatch.setattr(links, "default_runner", lambda core: lambda paths: (True, "passed"))
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    return repo


def _models(monkeypatch, unchanged: bool, diagnosis=None) -> None:
    judge = SimpleNamespace(same_meaning=lambda **shown: repin.Meaning(unchanged, "said so", 1.0))
    monkeypatch.setattr(repin, "open_judge", lambda core: judge)
    found = None if diagnosis is None else repin.Diagnosis(**diagnosis)
    diagnoser = SimpleNamespace(diagnose=lambda **kw: (found, "no diagnosis"))
    monkeypatch.setattr(repin, "open_diagnoser", lambda core: diagnoser)


def _settle(repo: Path) -> None:
    core = open_core(repo)
    stale.settle_drift(core, "s1", stale.stale_rows(core))


def _state(repo: Path) -> str:
    return [s for s in open_core(repo).link_states(["SR-001"]) if s.link.id == LINK][0].state


def test_ex1_a_refactor_that_keeps_the_meaning_is_repinned_with_no_card(
        project: Path, monkeypatch) -> None:
    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    _models(monkeypatch, True)
    _settle(project)
    assert _state(project) == "current" and asked(project, "s1") == []
    (entry,) = open_core(project).log_read("events", ["repin"])
    assert "meaning unchanged (sonnet)" in entry.payload["note"]


def test_failing_tests_leave_the_link_stale_and_unrepinned(project: Path, monkeypatch) -> None:
    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    _models(monkeypatch, True)
    monkeypatch.setattr(links, "default_runner", lambda core: lambda paths: (False, "failed"))
    _settle(project)
    assert _state(project) == "stale"


def test_ex2_a_change_to_what_the_requirement_says_files_a_card(
        project: Path, monkeypatch) -> None:
    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    _models(monkeypatch, False, dict(outcome="owner", explanation="add now means something else",
                                     topic="Adds numbers", options=("keep", "change"),
                                     consequences=("a", "b"), why="x"))
    _settle(project)
    (card,) = asked(project, "s1")
    assert card["link"] == LINK and card["by"] == "diagnosis" and _state(project) == "stale"


def test_ex2_a_confirmed_example_with_no_test_left_files_a_card_once(
        project: Path, monkeypatch) -> None:
    test = project / "tests" / "test_a.py"
    test.parent.mkdir()
    test.write_text("def test_a():\n    assert True\n", "utf-8")
    core = open_core(project)
    core.add_link("SR-001", "verified_by", Target(test="tests/test_a.py::test_a"), example="EX-1")
    test.unlink()
    core.status = lambda ids: {i: SimpleNamespace(confirmation="confirmed") for i in ids}
    stale.ask_lost_tests(core, "s1")
    stale.ask_lost_tests(core, "s1")
    (card,) = asked(project, "s1")
    assert card["record"] == "SR-001" and "EX-1" in card["issue"]


def test_ex4_a_wording_only_change_is_an_unconfirmed_edit_and_the_link_repinned(
        project: Path, monkeypatch) -> None:
    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    _models(monkeypatch, False, dict(outcome="reword", explanation="same sum, other words",
                                     topic="Adds numbers",
                                     proposed_wording="add returns the total."))
    _settle(project)
    core = open_core(project)
    assert core.index()["SR-001"].fields["statement"] == "add returns the total."
    assert _state(project) == "current" and asked(project, "s1") == []


SR2 = SR1.replace("SR-001", "SR-002").replace("Adds numbers", "Never reorders").replace(
    "add returns the sum.", "operands are never reordered.")


def _contradiction(monkeypatch, other: str) -> None:
    _models(monkeypatch, False, dict(
        outcome="contradicts", explanation="adding now swaps the operands", topic="Adds numbers",
        options=("Adding wins", "Never reordering wins"), consequences=("a", "b"), why="x",
        other=other))


def test_ex3_two_confirmed_records_that_contradict_raise_one_card_which_wins(
        project: Path, write_record, monkeypatch) -> None:
    write_record(project, SR2)
    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    _contradiction(monkeypatch, "SR-002")
    monkeypatch.setattr(type(open_core(project)), "status", lambda self, ids: {
        i: SimpleNamespace(confirmation="confirmed") for i in ids})
    _settle(project)
    _settle(project)
    (card,) = asked(project, "s1")
    assert card["by"] == "contradiction" and card["options"] == ["Adding wins",
                                                                "Never reordering wins"]
    assert _state(project) == "stale"      # nothing is repinned while the owner decides


def test_ex3_a_contradiction_with_an_unconfirmed_record_files_no_card(
        project: Path, write_record, monkeypatch) -> None:
    write_record(project, SR2)
    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    _contradiction(monkeypatch, "SR-002")
    _settle(project)
    assert asked(project, "s1") == [] and _state(project) == "stale"


@pytest.mark.sr("SR-245")
def test_sr174_an_http_error_from_the_judge_is_waiting_not_unresolved(
        project: Path, monkeypatch) -> None:
    from plumb.contracts import DispatchError

    class Broken:
        name = "api"

        def run(self, *a, **k):
            raise DispatchError("request", "HTTP 400 bad key")

    (project / "src" / "calc.py").write_text(REFACTORED, "utf-8")
    monkeypatch.setattr(repin, "open_judge", lambda core: repin.ModelMeaningJudge(Broken()))
    core = open_core(project)
    waiting: set[str] = set()
    said = stale.settle_drift(core, "s1", stale.stale_rows(core), waiting)
    assert waiting == {"SR-001"} and said and _state(project) == "stale"
