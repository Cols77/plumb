"""SR-390: one list of every loop of the project, from any checkout."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from plumb import cli
from plumb.understand import cmd_intent, files, gate, loops

from capture.capture_helpers import log_prompt
from conftest import git
from understand.test_judge_job import intent_text, requirement_text

pytestmark = pytest.mark.sr("SR-390")

SESSION = "sa"
DIGEST = "sha256:" + "a" * 64
LIVE = {SESSION: {"status": "busy", "cwd": ""}}


def _loop(root: Path, session: str = SESSION, digest: str = DIGEST, **fields: Any) -> Path:
    path = cmd_intent.open_loop(root, session, digest)
    data = files.read_json(path)
    data.update(fields)
    cmd_intent.save(path, data)
    return path


def _passed(*stages: str) -> dict[str, Any]:
    return {s: {"state": "passed", "at": "2026-11-01T10:00:00Z"} for s in stages}


def _worktree(repo: Path, tmp_path: Path, name: str = "wt") -> Path:
    wt = tmp_path / name
    git(repo, "worktree", "add", "-q", "-b", f"intent/{name}", str(wt))
    return wt


def _only(data: dict[str, Any]) -> dict[str, Any]:
    assert len(data["rows"]) == 1, data["rows"]
    return data["rows"][0]


def test_ex1_another_worktree_lists_a_loop_at_plan_with_what_is_left(
        repo: Path, tmp_path: Path, write_record: Any) -> None:
    write_record(repo, intent_text(1, "q", "Lists every loop."))
    stages = {"clarify": {"state": "passed", "at": "2026-11-01T10:00:00Z"},
              "plan": {"state": "open"}, "build": {"state": "open"}}
    _loop(repo, intent="INT-001", stages=stages,
          tasks={"label": "writing", "done": 3, "total": 7, "left": ["the notes"]})
    row = _only(loops.listing(_worktree(repo, tmp_path), agents=LIVE))
    assert row["goal"] == "Lists every loop." and row["progress"] == "plan · 3/7"
    assert row["left"][-2:] == ["build", "proven"] and row["branch"] == "main"


def test_ex2_main_lists_a_loop_opened_in_a_worktree(repo: Path, tmp_path: Path) -> None:
    wt = _worktree(repo, tmp_path)
    _loop(wt)
    row = _only(loops.listing(repo, agents=LIVE))
    assert row["branch"] == "intent/wt" and row["root"] == wt.as_posix()


def test_ex3_no_intent_yet_the_goal_is_the_opening_words_on_one_line(repo: Path) -> None:
    words = "/plumb intent " + "make the list\nbetter " * 12
    digest = log_prompt(repo, words, session=SESSION)
    _loop(repo, digest=digest)
    goal = _only(loops.listing(repo, agents=LIVE))["goal"]
    assert goal.startswith("make the list better make") and "\n" not in goal
    assert len(goal) <= 100


def test_ex4_at_build_left_names_the_item_not_built_and_the_proof_not_shown(
        repo: Path, write_record: Any) -> None:
    write_record(repo, intent_text(1, "q", "Colours."))
    write_record(repo, requirement_text(1, "Colours show", "Colours show.", intent=1))
    _loop(repo, intent="INT-001", stages=_passed("clarify", "plan"),
          tasks={"label": "building", "done": 3, "total": 4, "left": ["the colours slice"]})
    left = _only(loops.listing(repo, agents=LIVE))["left"]
    assert "the colours slice" in left and "proof: Colours show" in left


def test_ex5_a_refused_gate_or_a_closed_gate_says_what_it_waits_for(repo: Path) -> None:
    path = _loop(repo, stopped="plan gate: 2 finding(s) to fix")
    assert "plan gate: 2 finding(s) to fix" in _only(loops.listing(repo, agents=LIVE))["waits"]
    data = files.read_json(path)
    data["stopped"] = None
    cmd_intent.save(path, data)
    gate.close(repo, SESSION, DIGEST, gate.INTENT_CHANGE)
    assert _only(loops.listing(repo, agents=LIVE))["waits"] == "the owner's answer"


def test_ex6_a_gone_sessions_loop_is_idle_below_with_its_date(repo: Path) -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _loop(repo, "gone", "sha256:" + "b" * 64, opened_at=old, stages={
        "clarify": {"state": "open"}, "plan": {"state": "open"}, "build": {"state": "open"}})
    _loop(repo)
    rows = loops.listing(repo, agents=LIVE)["rows"]
    assert [r["live"] for r in rows] == [True, False]
    assert rows[1]["idle_since"] == old[:10] and rows[1]["state"] == "idle"


def test_ex7_a_loop_taken_over_is_listed_once_at_its_holder(repo: Path) -> None:
    _loop(repo, intent="INT-001")
    assert cmd_intent.run("intent", ["adopt", "--root", str(repo), "--session", "sb"]) == 0
    row = _only(loops.listing(repo, agents={"sb": {"status": "busy"}}))
    assert row["session"] == "sb" and row["live"]


def test_ex8_no_loop_says_so(repo: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["loops", "--root", str(repo)]) == 0
    assert "no loop is open" in capsys.readouterr().out


def test_a_loop_held_in_a_worktree_reads_the_gate_and_words_where_the_session_runs(
        repo: Path, tmp_path: Path) -> None:
    digest = log_prompt(repo, "/plumb intent track the loops", session=SESSION)
    _loop(repo, digest=digest)
    gate.close(repo, SESSION, digest, gate.INTENT_CHANGE)
    (repo / ".plumb" / "session" / SESSION / "host.json").write_text("{}", encoding="utf-8")
    wt = _worktree(repo, tmp_path)
    path = cmd_intent.loop_path(wt, SESSION, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    files.write_json_atomic(path, files.read_json(cmd_intent.loop_path(repo, SESSION, digest)))
    held = cmd_intent.loop_path(repo, SESSION, digest)
    files.write_json_atomic(held, {**files.read_json(held), "handed_to": {"session": SESSION}})
    for lister in (repo, wt):
        row = _only(loops.listing(lister, agents=LIVE))
        assert row["waits"] == "the owner's answer" and row["goal"] == "track the loops"
        assert row["root"] == wt.as_posix()
    roots = [w.path for w in loops.checkouts(repo)]
    cwd = {SESSION: {"status": "busy", "cwd": repo.as_posix()}}
    assert loops.session_root(roots, SESSION, cwd, wt) == repo
    assert loops.session_root(roots, SESSION, None, wt) == repo


def test_listing_changes_nothing(repo: Path, tmp_path: Path) -> None:
    _loop(repo)
    _loop(_worktree(repo, tmp_path), "sb", "sha256:" + "c" * 64)

    def snapshot() -> dict[Path, tuple[int, bytes]]:
        return {p: (p.stat().st_mtime_ns, p.read_bytes())
                for r in (repo, tmp_path / "wt") for p in (r / ".plumb").rglob("*") if p.is_file()}

    before = snapshot()
    loops.listing(repo, agents=LIVE)
    assert snapshot() == before


def test_save_and_adopt_move_the_stamp(repo: Path, tmp_path: Path) -> None:
    wt = _worktree(repo, tmp_path)
    stamp = Path(loops.listing(wt, agents={})["stamp"])
    assert stamp == repo / ".git" / "plumb-loops.stamp"
    path = _loop(repo)
    first = stamp.read_text(encoding="utf-8")
    cmd_intent.save(path, files.read_json(path))
    second = stamp.read_text(encoding="utf-8")
    assert second != first
    assert cmd_intent.run("intent", ["adopt", "--root", str(wt), "--session", "sb"]) == 0
    assert stamp.read_text(encoding="utf-8") != second


def test_agents_unavailable_falls_back_to_recent_session_writes(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _loop(repo)
    monkeypatch.setattr(loops, "claude_sessions", lambda: None)
    assert _only(loops.listing(repo))["live"] is True
    old = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _only(loops.listing(repo, now=old))["live"] is False


def test_finished_loop_not_listed(repo: Path) -> None:
    _loop(repo, stages=_passed("clarify", "plan", "build"))
    assert loops.listing(repo, agents=LIVE)["rows"] == []


def test_find_ambiguous_words_list_candidates_and_change_nothing(repo: Path) -> None:
    _loop(repo, "sa", "sha256:" + "a" * 64)
    _loop(repo, "sb", "sha256:" + "b" * 64)
    data = loops.listing(repo, agents=LIVE)
    before = [json.dumps(r, sort_keys=True) for r in data["rows"]]
    with pytest.raises(LookupError) as raised:
        loops.find(data["rows"], "intent loop")
    assert str(raised.value).count("\n") == 2 and "aaaaaaaaaaaa" in str(raised.value)
    assert loops.find(data["rows"], "bbbbbb")["session"] == "sb"
    assert [json.dumps(r, sort_keys=True) for r in data["rows"]] == before


def test_json_has_counts_per_type(repo: Path, capsys: pytest.CaptureFixture) -> None:
    _loop(repo)
    assert cli.main(["loops", "--json", "--root", str(repo)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["counts"]["intent"] == {"live": 0, "idle": 1}
    assert data["counts"]["debug"] == {"live": 0, "idle": 0} and data["idle"] == 1
