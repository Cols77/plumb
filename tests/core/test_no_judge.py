"""SR-174: with no judge reachable iaso says so once and the step waits, deciding nothing
by rule; work that needs no judge goes on. Judges are stubbed unreachable, then back."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.stale_asked import asked
from iaso import links, stale
from iaso.api import open_core
from iaso.capture import autoapprove
from iaso.contracts import Target
from iaso.understand import repin

pytestmark = pytest.mark.sr("SR-245")

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


def _vcs(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_ex1_auto_approval_without_a_key_says_so_once_and_approves_nothing(
        repo: Path, write_record, monkeypatch) -> None:
    from understand.fakes import FakeDispatcher
    from understand.test_judge_job import build_job, make_world, verdict_answer

    from iaso.understand import judge, verdict

    ids = make_world(repo, write_record, 1)
    core = open_core(repo)
    on = SimpleNamespace(configured=True, effective=False, reason="the JEV credential is absent")
    monkeypatch.setattr(autoapprove, "auto_approve_state", lambda core: on)
    monkeypatch.setattr(autoapprove, "jev_ready", lambda core: (False, "no key"))
    model = FakeDispatcher({"judge": verdict_answer(("SR-001", "supported", 0.9))})
    job = build_job(core, ids)
    done = verdict.cascade(core, job, system="judge", schema={}, jev=None, dispatcher=model)
    assert "auto-approval is waiting" in done.line and "no key" in done.line
    applied = judge.apply(core, job, done.answer)
    assert [e for e in applied.entries if e["payload"].get("by") == "auto-jev"] == []
    again = verdict.cascade(core, job, system="judge", schema={}, jev=None, dispatcher=model)
    assert again.line == ""   # once per session


@pytest.fixture
def project(repo: Path, write_record, monkeypatch) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py", symbol="add"))
    _vcs(repo, "add", "-A")
    _vcs(repo, "commit", "-q", "-m", "setup")
    monkeypatch.setattr(links, "default_runner", lambda core: lambda paths: (True, "passed"))
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return b + a\n", "utf-8")
    return repo


def _state(repo: Path) -> str:
    return [s for s in open_core(repo).link_states(["SR-001"])][-1].state


def test_ex1_and_3_stale_check_waits_then_completes_when_the_judge_is_back(
        project: Path, monkeypatch) -> None:
    monkeypatch.setattr(repin, "open_judge", lambda core: None)
    monkeypatch.setattr(repin, "judge_gap", lambda core: "no key")
    core = open_core(project)
    rows = stale.stale_rows(core)
    first = stale.settle_drift(core, "s1", rows)
    assert len(first) == 1 and "the stale check is waiting" in first[0] and "no key" in first[0]
    assert _state(project) != "current" and asked(project, "s1") == []
    assert stale.settle_drift(core, "s1", rows) == []   # said once
    judge = SimpleNamespace(same_meaning=lambda **shown: repin.Meaning(True, "kept", 1.0))
    monkeypatch.setattr(repin, "open_judge", lambda core: judge)
    assert stale.settle_drift(core, "s1", rows) == []   # the judge is back: no line
    assert _state(project) == "current"                  # and the step completed


def test_ex2_work_without_a_stale_link_needs_no_judge(project: Path, monkeypatch) -> None:
    def refuse(core):
        raise AssertionError("no judge is asked when nothing is stale")

    monkeypatch.setattr(repin, "open_judge", refuse)
    assert stale.settle_drift(open_core(project), "s1", []) == []
