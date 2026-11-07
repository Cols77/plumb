"""SR-325: every plumb failure leaves one debug case the moment it happens; ``plumb debug``
lists them beside the stale links, reruns each once and counts them. Models are stubbed."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.stale_asked import asked
from plumb import debug, stale
from plumb.api import open_core
from plumb.contracts import Job, JobError, JobResult, Target
from plumb.hosts.claude_code import hookio
from plumb.links import NO_MODEL, AfterTests
from plumb.understand import worker

pytestmark = pytest.mark.sr("SR-325")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum{suffix}.
---
"""
LINK = "DEC-001#0"


@pytest.fixture
def stale_link(repo: Path, write_record) -> Path:
    """A decision pinned to SR-001, which was reworded since (the link is stale)."""
    write_record(repo, SR1.format(suffix=""))
    write_record(repo, "---\nid: DEC-001\ntitle: Round?\nquestion: Round?\nchosen: No\n"
                       "alternatives:\n- Yes\n---\n")
    open_core(repo).add_link("DEC-001", "decides", Target(record="SR-001"))
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "setup"], cwd=repo, check=True,
                   capture_output=True)
    write_record(repo, SR1.format(suffix=" of two numbers"))
    return repo


def _repin(monkeypatch, step: AfterTests) -> list[str]:
    calls: list[str] = []

    def fake(core, record, **kw):
        calls.append(record)
        return step

    monkeypatch.setattr("plumb.links.repin_after_tests", fake)
    return calls


def _rows(repo: Path) -> dict[str, dict]:
    return {r["id"]: r for r in debug.all_cases(repo)}


def test_ex1_a_hook_error_is_one_case_and_the_turn_goes_on(repo: Path) -> None:
    def boom(ctx):
        raise RuntimeError("the hook broke")

    out = io.StringIO()
    for _ in range(2):  # the same error twice is still one case
        code = hookio.run_hook("stop", boom, stdin=io.StringIO(json.dumps({"cwd": str(repo)})),
                               stdout=out, root=repo)
        assert code == 0
    (row,) = debug.open_cases(repo)
    assert row["kind"] == "hook-error" and row["target"] == "stop"
    assert "the hook broke" in row["detail"] and "RuntimeError" in row["log"]
    assert row["state"] == "open" and "debug" not in out.getvalue()


def test_ex2_a_refused_link_is_one_case_naming_it_and_asks_nothing(
        stale_link: Path, monkeypatch) -> None:
    core = open_core(stale_link)
    _repin(monkeypatch, AfterTests(refused=[(LINK, "the meaning changed: rounded"),
                                            ("DEC-002#0", NO_MODEL)]))
    said = stale.settle_drift(core, "s1", [SimpleNamespace(record="SR-001")])
    (row,) = debug.open_cases(stale_link)
    assert row["kind"] == "stale-refused" and row["target"] == LINK
    assert "rounded" in row["detail"] and said == []  # no model: held, no case (SR-220 EX-5)
    assert asked(stale_link, "s1") == []


def test_ex3_each_case_is_rerun_once_and_listed_with_the_counts(
        stale_link: Path, monkeypatch, capsys) -> None:
    debug.open_case(stale_link, id=LINK, kind="stale-refused", target=LINK, detail="refused")
    debug.open_case(stale_link, id="hook-x", kind="hook-error", target="stop", detail="boom")
    debug.open_case(stale_link, id="job-j", kind="job-failed", target="j", detail="read failed")
    calls = _repin(monkeypatch, AfterTests(refused=[(LINK, "still refused")]))
    assert debug.run("debug", ["--root", str(stale_link)]) == 1
    out = capsys.readouterr().out
    assert calls == ["DEC-001"] and "3 cases, 0 resolved, 3 still" in out
    assert f"{LINK}: open: still refused" in out
    assert "hook-x: open: boom" in out and "job-j: open: read failed" in out


def test_ex4_a_case_whose_rerun_passes_is_resolved_and_counted_next_time(
        stale_link: Path, monkeypatch, capsys) -> None:
    debug.open_case(stale_link, id=LINK, kind="stale-refused", target=LINK, detail="refused")
    _repin(monkeypatch, AfterTests(changes=[{"link": LINK, "tier": "tests pass"}]))
    assert debug.run("debug", ["--root", str(stale_link)]) == 0
    assert _rows(stale_link)[LINK]["state"] == "resolved" and debug.open_cases(stale_link) == []
    capsys.readouterr()
    _repin(monkeypatch, AfterTests())
    debug.run("debug", ["--root", str(stale_link)])
    assert "1 cases, 1 resolved, 0 still" in capsys.readouterr().out
    debug.open_case(stale_link, id="hook-x", kind="hook-error", target="stop", detail="boom")
    debug.run("debug", ["--root", str(stale_link), "done", "hook-x"])
    assert debug.open_cases(stale_link) == []


def test_ex5_the_third_failure_in_a_row_is_one_case(repo: Path) -> None:
    run = worker._Pass(open_core(repo), "s1", "tok")
    job = Job(id="read-0123", kind="read", session="s1")
    bad = JobResult(job=job.id, status="error", error=JobError(step="dispatch", message="x"))
    for _ in range(2):
        run._count(job, bad)
    assert debug.open_cases(repo) == []
    run._count(job, bad)
    run._count(job, bad)
    (row,) = debug.open_cases(repo)
    assert row["kind"] == "job-failed" and row["target"] == "read-0123"
    assert "dispatch" in row["log"]


def test_ex1_one_cause_seen_by_two_processes_is_one_case(repo: Path) -> None:
    """The same traceback with another temp file's pid is the same case (one fix, not two)."""
    for pid in ("25132", "4410"):
        debug.hook_error(repo, "stop", f'File "x.py", line 3\nPermissionError: '
                                       f"'.status.json.{pid}.tmp' -> 'status.json'")
    assert len(debug.open_cases(repo)) == 1
