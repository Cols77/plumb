"""SR-392: the evaluate loop in the loop list, one row per run still going."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import pytest

from plumb import debug
from plumb.evaluate import issues, loop
from plumb.understand import loops

pytestmark = pytest.mark.sr("SR-392")

TASK = NS(name="simple")


@pytest.fixture(autouse=True)
def _doubles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plumb.api.open_core", lambda root: object())
    monkeypatch.setattr("plumb.debug.all_cases", lambda root: [])
    monkeypatch.setattr(issues, "open_cases", lambda root, found: [f"e{i}" for i in found])


def _run(root: Path, seen: list[dict[str, Any]], issue_lists: list[list[int]]) -> Any:
    runs: list[int] = []

    def run(r: Path, task: Any, *, model: str, **kw: Any) -> Any:
        seen.append(loop.rows(root)[0])
        runs.append(1)
        return NS(issues=issue_lists[len(runs) - 1], score={})
    return run


def _fix(root: Path, seen: list[dict[str, Any]], state: str = "fixed") -> Any:
    def fix(core: Any, case: Any) -> Any:
        seen.append(loop.rows(root)[0])
        return NS(state=state, branch="debug/x", detail="d")
    return fix


def test_ex1_first_fix_round_of_two_reads_round_1_of_2_with_problems_filed(
        tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    loop.run_loop(tmp_path, TASK, model="haiku", rounds=3, run=_run(tmp_path, seen, [[1, 2], []]),
                  fix=_fix(tmp_path, seen), merge=lambda r, b: "")
    row = seen[1]
    assert row["progress"] == "simple · haiku · round 1 of 2 · 2 problems filed"
    assert row["left"][:2] == ["the fix round", "the rerun"] and row["live"]


def test_ex2_a_held_merge_stops_the_run_and_the_row_says_why(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    loop.run_loop(tmp_path, TASK, model="haiku", rounds=3, run=_run(tmp_path, seen, [[1]]),
                  fix=_fix(tmp_path, seen), merge=lambda r, b: "SR-1 is unconfirmed")
    (row,) = loop.rows(tmp_path)
    assert row["waits"] == "stopped: the merge of debug/x is held: SR-1 is unconfirmed"
    assert not row["live"] and row["state"] == "idle"


def test_ex3_an_ended_run_is_not_listed(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    loop.run_loop(tmp_path, TASK, model="haiku", rounds=2, run=_run(tmp_path, seen, [[]]),
                  fix=_fix(tmp_path, seen), merge=lambda r, b: "")
    assert seen and loop.rows(tmp_path) == []


def test_rounds_zero_run_is_listed_while_it_runs(tmp_path: Path) -> None:
    name = loop.start(tmp_path, TASK, "haiku", 0)
    (row,) = loop.rows(tmp_path)
    assert row["progress"] == "simple · haiku · first run" and row["left"] == ["the run's score"]
    loop.note(tmp_path, name, ended=True)
    assert loop.rows(tmp_path) == []


def test_a_rerun_reads_after_round_1_of_2(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    loop.run_loop(tmp_path, TASK, model="haiku", rounds=3, run=_run(tmp_path, seen, [[1], []]),
                  fix=_fix(tmp_path, seen), merge=lambda r, b: "")
    assert seen[0]["progress"] == "simple · haiku · first run"
    assert seen[2]["progress"].startswith("simple · haiku · rerun after round 1 of 2")


def test_the_fixes_after_the_last_run_never_read_past_the_rounds_asked(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    loop.run_loop(tmp_path, TASK, model="haiku", rounds=3,
                  run=_run(tmp_path, seen, [[1], [1], [1]]), fix=_fix(tmp_path, seen),
                  merge=lambda r, b: "")
    last = [r for r in seen if "last run" in r["progress"]]
    assert last and last[0]["left"] == ["the fixes of the last run"]
    assert not any("round 3 of 2" in r["progress"] for r in seen)


def test_note_and_case_writes_move_the_stamp(repo: Path) -> None:
    stamp = Path(loops.listing(repo, agents={})["stamp"])

    def moved(write: Any) -> None:
        before = stamp.read_text("utf-8") if stamp.exists() else ""
        write()
        assert stamp.read_text("utf-8") != before

    moved(lambda: loop.note(repo, "n", task="simple"))
    monkey_case = {"id": "c", "state": "open"}
    moved(lambda: debug._write_case(repo, monkey_case))
    moved(lambda: debug._update(repo, ["c"], stage="fix"))
    assert json.loads((repo / ".plumb/cache/evaluate/n.json").read_text())["task"] == "simple"
