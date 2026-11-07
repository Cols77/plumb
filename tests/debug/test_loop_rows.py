"""SR-391: the debug loop in the loop list, one row per problem plumb is fixing itself."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from plumb import debug, selfdebug
from plumb.api import open_core
from plumb.understand import loops
from plumb.understand.repin import Meaning
from debug.staged import ok_stages  # SR-388: the diagnosis and the review, scripted

from debug.test_selffix import (CASE, TEST, Fixer, Judge, Runner, fixes_add,  # noqa: F401
                                fixes_nothing, no_real_models, plumb_repo)

pytestmark = pytest.mark.sr("SR-391")


def _case(root: Path, id: str = "c1", **fields: Any) -> None:
    debug._write_case(root, {"id": id, "kind": "hook-error", "target": "stop",
                             "detail": "ValueError: the list is empty\nat line 3",
                             "state": "open", **fields})


def _only(root: Path) -> dict[str, Any]:
    rows = debug.loop_rows(root)
    assert len(rows) == 1, rows
    return rows[0]


def test_ex1_fix_written_tests_running_with_landing_and_live_check_left(tmp_path: Path) -> None:
    _case(tmp_path, stage="tests", pid=os.getpid())
    row = _only(tmp_path)
    assert row["goal"] == "ValueError: the list is empty" and row["live"]
    assert row["progress"] == "fix written, tests running"
    assert row["left"] == ["landing", "the live check"]


def test_ex2_landed_not_checked_live(tmp_path: Path) -> None:
    _case(tmp_path, state="resolved", branch="debug/c1", landed="abc123")
    row = _only(tmp_path)
    assert row["progress"] == "landed, not checked live" and row["left"] == ["the live check"]
    assert not row["live"]


def test_ex3_a_report_or_owner_question_waits_for_the_owner(tmp_path: Path) -> None:
    _case(tmp_path, "r", report="Missing: a test")
    _case(tmp_path, "o", stage="owner")
    rows = debug.loop_rows(tmp_path)
    assert [r["waits"] for r in rows] == ["the owner", "the owner"]
    assert {r["progress"] for r in rows} == {"waits for the owner"}


def test_ex4_resolved_and_proven_is_not_listed(tmp_path: Path) -> None:
    _case(tmp_path, state="resolved", landed="abc", proven="def")
    _case(tmp_path, "plain", state="resolved")
    assert debug.loop_rows(tmp_path) == []


def test_a_dead_pid_reads_idle(tmp_path: Path) -> None:
    _case(tmp_path, stage="fix", round=2, pid=2 ** 22 + 12345)
    row = _only(tmp_path)
    assert not row["live"] and row["progress"] == "open, fix not started"
    assert row["state"] == "idle" and row["idle_since"]


def test_a_live_fix_names_its_round(tmp_path: Path) -> None:
    _case(tmp_path, stage="fix", round=2, pid=os.getpid())
    row = _only(tmp_path)
    assert row["progress"] == "fix being written (round 2)" and row["left"][0] == "tests"


def test_known_issue_title_is_the_goal(tmp_path: Path) -> None:
    reg = tmp_path / ".plumb" / "known-issues.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text('{"issues": [{"id": "KI-1", "symptom": "x", "title": "The list is blank"}]}',
                   "utf-8")
    _case(tmp_path, issue="KI-1")
    assert _only(tmp_path)["goal"] == "The list is blank"


def test_a_fix_committed_not_landed_is_listed_as_waiting_to_land(tmp_path: Path) -> None:
    _case(tmp_path, state="resolved", branch="debug/x")
    _case(tmp_path, "rp", kind="repin", state="resolved", branch="debug/rp")
    rows = debug.loop_rows(tmp_path)
    assert {r["progress"] for r in rows} == {"fix committed, waits to land"}
    assert all(r["left"] == ["landing", "the live check"] for r in rows)


def test_a_problem_that_came_back_reads_open_fix_not_started(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plumb.debug._queue_fix", lambda *a: None)
    _case(tmp_path, state="resolved", stage="tests", round=1, pid=os.getpid(),
          report="Missing: x", symptom=debug._same("hook-error:stop:ValueError: the list is empty"))
    debug.open_case(tmp_path, id="c1", kind="hook-error", target="stop",
                    detail="ValueError: the list is empty", session="s")
    row = _only(tmp_path)
    assert row["progress"] == "open, fix not started"
    assert row["left"] == ["the fix", "tests", "landing", "the live check"]
    (case,) = debug.all_cases(tmp_path)
    assert case["history"][-1]["report"] == "Missing: x" and "report" not in case


def test_selfdebug_stamps_tests_stage_before_verify(plumb_repo: Path) -> None:
    seen: list[dict[str, Any]] = []
    fixer = Fixer(fixes_add)
    runner = Runner(fixer)

    def spy(paths: Any) -> Any:
        seen.append(next(c for c in debug.all_cases(plumb_repo) if c["id"] == CASE))
        return runner(paths)

    case = next(c for c in debug.open_cases(plumb_repo) if c["id"] == CASE)
    selfdebug.fix(open_core(plumb_repo), case, fixer=fixer, runner=spy,
                  judge=Judge(Meaning(True, "same")), **ok_stages())
    assert seen[0]["stage"] == "tests" and seen[0]["round"] == 1 and seen[0]["pid"] == os.getpid()


def _after(plumb_repo: Path, fixer: Fixer, answer: Meaning) -> dict[str, Any]:
    case = next(c for c in debug.open_cases(plumb_repo) if c["id"] == CASE)
    selfdebug.fix(open_core(plumb_repo), case, fixer=fixer, runner=Runner(fixer),
                  judge=Judge(answer), **ok_stages())
    return next(c for c in debug.all_cases(plumb_repo) if c["id"] == CASE)


def test_fix_end_clears_the_stage(plumb_repo: Path) -> None:
    fixed = _after(plumb_repo, Fixer(fixes_add), Meaning(True, "same"))
    assert fixed["stage"] == "" and fixed["pid"] == 0


def test_a_reported_fix_clears_the_stage_and_waits_for_the_owner(plumb_repo: Path) -> None:
    case = _after(plumb_repo, Fixer(fixes_nothing), Meaning(True, "same"))
    assert case["stage"] == "" and case["pid"] == 0
    assert debug.loop_rows(plumb_repo)[0]["waits"] == "the owner"


def test_an_owner_outcome_leaves_stage_owner(plumb_repo: Path) -> None:
    def rewords(wt: Path) -> None:
        fixes_add(wt)
        (wt / ".plumb" / "requirements" / "SR-001.md").write_text(
            "---\nid: SR-001\ntitle: Adds numbers\nfeature: FEAT-001\n"
            "statement: add returns the sum, rounded.\n---\n", "utf-8")

    case = _after(plumb_repo, Fixer(rewords), Meaning(False, "rounded now"))
    assert case["stage"] == "owner" and case["pid"] == 0


def test_listing_merges_debug_rows(plumb_repo: Path) -> None:
    rows = loops.listing(plumb_repo, agents={})["rows"]
    assert [r["kind"] for r in rows] == ["debug"]
