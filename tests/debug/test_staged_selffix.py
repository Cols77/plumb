# ruff: noqa: F811
"""SR-388: the self-fix of a debug case runs each round as three stages by three agent runs
(diagnosis, fix, review), then iaso's own checks; a failed round hands its findings to the
next; open cases are worked side by side with their test runs in turn. Stages and runner are
scripted, git is real, no model is called."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from debug.staged import CAUSE, OK, Fixer, Stage, diagnosis, not_ok
from debug.test_selffix import (  # noqa: F401 - fixtures
    BRANCH,
    CASE,
    Judge,
    Runner,
    _git,
    _state,
    fixes_add,
    fixes_nothing,
    no_real_models,
    iaso_repo,
)

from iaso import debug, selfdebug, stale
from iaso import heavy as heavy_mod
from iaso.api import open_core
from iaso.understand import jobs, queue, worker
from iaso.understand import selfdebug as kind
from iaso.understand.repin import Meaning

pytestmark = pytest.mark.sr("SR-388")

FINDING = "the fixer's test does not exercise the cause the diagnosis named"


def _run(repo: Path, fixer: Fixer, diag: Stage, review: Stage, rounds: int = 3):
    core = open_core(repo)
    case = next(c for c in debug.open_cases(repo) if c["id"] == CASE)
    runner = Runner(fixer)
    out = selfdebug.fix(core, case, rounds=rounds, fixer=fixer, diagnoser=diag,
                        reviewer=review, runner=runner, judge=Judge(Meaning(True, "same", 0.9)))
    return out, runner


def _models(repo: Path) -> list[dict]:
    return next(c for c in debug.all_cases(repo) if c["id"] == CASE)["models"]


def _commits(repo: Path) -> str:
    return _git(repo, "rev-list", "--count", f"main..{BRANCH}").strip()


def test_ex1_the_case_names_three_stages_with_their_models_and_the_review_is_its_own_run(
        iaso_repo: Path) -> None:
    trail: list = []
    fixer = Fixer(trail, fixes_add)
    diag, review = Stage("diagnosis", [diagnosis()], trail), Stage("review", [OK], trail)
    out, _ = _run(iaso_repo, fixer, diag, review)
    assert out.state == "fixed", out.detail
    models = _models(iaso_repo)
    assert [m["stage"] for m in models] == [
        "evidence", "round 1 diagnosis", "round 1 fix", "round 1 review"]
    got = {m["stage"]: m for m in models}
    assert got["round 1 diagnosis"]["model"] == diag.models[0]
    assert got["round 1 fix"]["model"] == fixer.models[0]
    assert got["round 1 review"]["model"] == review.models[0]
    assert all(got[f"round 1 {s}"]["level"] == "sonnet" for s in ("diagnosis", "fix", "review"))
    # three separate runs, in order; the review is given the cause, the change and the records
    assert trail == [("diagnosis", 1), ("fix", 1), ("review", 1)]
    assert CAUSE in fixer.seen[0]                      # the fixer's input carries the diagnosis
    assert CAUSE in review.seen[0] and "return a + b" in review.seen[0]
    assert "SR-001" in review.seen[0]
    assert review.seen[0] != fixer.seen[0]


def test_ex1_a_diagnosis_that_changes_a_file_fails_the_round_and_is_undone(
        iaso_repo: Path) -> None:
    trail: list = []
    fixer = Fixer(trail, fixes_add)

    def writes(wt: Path) -> None:
        (wt / "src" / "iaso" / "calc.py").write_text("def add(a, b):\n    return 0\n", "utf-8")

    diag = Stage("diagnosis", [diagnosis()], trail, effect=writes)
    review = Stage("review", [OK], trail)
    out, _ = _run(iaso_repo, fixer, diag, review, rounds=1)
    assert out.state == "reported" and out.rounds[0].startswith("round 1:")
    assert fixer.models == [] and review.models == []         # nothing after a bad diagnosis
    wt = iaso_repo / ".iaso" / "wt" / "debug-hook-stop-1"
    assert "BUG" in (wt / "src" / "iaso" / "calc.py").read_text("utf-8")
    assert _git(wt, "status", "--porcelain").strip() == "" and _commits(iaso_repo) == "0"


def test_ex2_a_review_that_says_not_ok_fails_the_round_and_the_next_is_given_the_finding(
        iaso_repo: Path) -> None:
    trail: list = []
    fixer = Fixer(trail, fixes_add)
    runs_at: list[int] = []
    out_runner: list[Runner] = []

    class Diag(Stage):
        def __call__(self, **kw):
            runs_at.append(len(out_runner[0].calls) if out_runner else 0)
            return super().__call__(**kw)

    diag = Diag("diagnosis", [diagnosis()], trail)
    review = Stage("review", [not_ok(FINDING), OK], trail)
    core = open_core(iaso_repo)
    case = next(c for c in debug.open_cases(iaso_repo) if c["id"] == CASE)
    runner = Runner(fixer)
    out_runner.append(runner)
    out = selfdebug.fix(core, case, fixer=fixer, diagnoser=diag, reviewer=review,
                        runner=runner, judge=Judge(Meaning(True, "same", 0.9)))
    assert out.state == "fixed" and len(out.rounds) == 1
    assert out.rounds[0].startswith("round 1:") and FINDING in out.rounds[0]
    assert runs_at == [0, 0]            # no test ran for a round whose review said not ok
    for stage in (diag, fixer, review):  # round 2: all three stages are given round 1
        assert FINDING in (stage.seen[1] if stage is not fixer else fixer.seen[1])
    assert diag.models == [fixer.models[0], fixer.models[1]] and len(diag.models) == 2
    assert diag.models[0] != diag.models[1]           # one level up after the failed round
    assert trail == [("diagnosis", 1), ("fix", 1), ("review", 1),
                     ("diagnosis", 2), ("fix", 2), ("review", 2)]


def test_ex2_a_not_ok_review_commits_nothing(iaso_repo: Path) -> None:
    trail: list = []
    out, runner = _run(iaso_repo, Fixer(trail, fixes_add),
                       Stage("diagnosis", [diagnosis()], trail),
                       Stage("review", [not_ok(FINDING)], trail), rounds=1)
    assert out.state == "reported" and FINDING in out.detail
    assert _commits(iaso_repo) == "0" and _state(iaso_repo) == "open"
    assert runner.calls == []


def test_ex4_three_rounds_failed_by_the_review_or_the_checks_end_as_a_report(
        iaso_repo: Path) -> None:
    trail: list = []
    fixer = Fixer(trail, fixes_add, fixes_nothing, fixes_add)
    diag = Stage("diagnosis", [diagnosis()], trail)
    review = Stage("review", [not_ok(FINDING), OK, not_ok("third finding")], trail)
    out, _ = _run(iaso_repo, fixer, diag, review)
    assert out.state == "reported" and len(out.rounds) == 3
    assert FINDING in out.rounds[0] and "third finding" in out.rounds[2]
    for stage in (diag, review):
        assert len(stage.models) == 3
    assert fixer.models == diag.models == review.models == ["sonnet", "opus", "fable"]
    assert len(diag.kws[2]["previous"]) == 2
    (row,) = [c for c in debug.open_cases(iaso_repo) if c["id"] == CASE]
    for n in (1, 2, 3):
        assert f"round {n}" in row["report"]
    assert "Nothing was committed" in row["report"]
    assert [m["stage"] for m in row["models"]][-3:] == [
        "round 3 diagnosis", "round 3 fix", "round 3 review"]
    assert _commits(iaso_repo) == "0" and _state(iaso_repo) == "open"
    wt = iaso_repo / ".iaso" / "wt" / "debug-hook-stop-1"
    assert _git(wt, "status", "--porcelain").strip()    # the last try stays in the worktree


# --- side by side -----------------------------------------------------------------------

@pytest.mark.parametrize("inherited", [False, True])
def test_two_threads_calling_heavy_in_one_process_take_turns(
        repo: Path, monkeypatch: pytest.MonkeyPatch, inherited: bool) -> None:
    monkeypatch.setattr(heavy_mod, "HEAVY_WAIT_S", 0.01)
    monkeypatch.delenv(heavy_mod.HELD, raising=False)
    if inherited:                       # a process started by `iaso heavy --`
        monkeypatch.setenv(heavy_mod.HELD, "1")
    state = {"in": 0, "peak": 0}
    mine = threading.Lock()

    def job(nested: bool) -> None:
        with heavy_mod.heavy(repo, "job"):
            with mine:
                state["in"] += 1
                state["peak"] = max(state["peak"], state["in"])
            if nested:                  # the same thread goes in again, without waiting
                with heavy_mod.heavy(repo, "inner"):
                    pass
            time.sleep(0.15)
            with mine:
                state["in"] -= 1

    threads = [threading.Thread(target=job, args=(n,)) for n in (True, False)]
    for t in threads:
        t.start()
        while t is threads[0] and not state["peak"]:     # the second starts once the first is in
            time.sleep(0.01)
    for t in threads:
        t.join(10)
    assert not any(t.is_alive() for t in threads)
    assert state["peak"] == 1
    assert not (repo / ".git" / "iaso-heavy.lock").exists()


def test_ex3_three_cases_limit_two_run_side_by_side_with_their_test_runs_in_turn(
        iaso_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    monkeypatch.setattr(heavy_mod, "HEAVY_WAIT_S", 0.01)
    monkeypatch.delenv(heavy_mod.HELD, raising=False)
    monkeypatch.delenv("IASO_JOB", raising=False)
    (iaso_repo / ".iaso" / "config.yaml").write_text(
        "understand:\n  parallel_calls: 2\n", encoding="utf-8")
    monkeypatch.setattr(worker, "start_detached", lambda root, session: None)
    for n, word in ((2, "beta"), (3, "gamma")):    # unlike symptoms: one case each
        debug.open_case(iaso_repo, id=f"hook-stop-{n}", kind="hook-error", target=f"stop-{word}",
                        detail=f"ValueError: add is wrong in {word} (SR-001)")
    core = open_core(iaso_repo)
    session = stale.current_session(iaso_repo)     # open_case queued the self-fix jobs there
    if len(jobs.queued(iaso_repo, session)) < 3:   # the fixture's case was opened before
        queue.enqueue(core, kind.build(core, session, case=CASE))
    assert sorted(j.inputs["case"] for j in jobs.queued(iaso_repo, session)) == [
        "hook-stop-1", "hook-stop-2", "hook-stop-3"]

    mine = threading.Lock()
    box = {"out": 0, "peak": 0, "run": 0, "run_peak": 0}
    wts: dict[str, Path] = {}
    seen_env: list[str | None] = []
    names: list[str] = []

    def count(key: str, peak: str, delta: int) -> None:
        with mine:
            box[key] += delta
            box[peak] = max(box[peak], box[key])

    def stage(name: str, answer: Any, step=None):
        def run(*, round, case, worktree, **kw):
            wts[case["id"]] = worktree
            names.append(name)
            seen_env.append(os.environ.get("IASO_JOB"))
            count("out", "peak", 1)
            try:
                time.sleep(0.2)
                if step:
                    step(case["id"], worktree)
            finally:
                count("out", "peak", -1)
            return dict(answer)
        return run

    def writes(cid: str, wt: Path) -> None:
        n = cid[-1]
        (wt / "tests").mkdir(exist_ok=True)
        (wt / "tests" / f"test_c{n}.py").write_text("def test_c():\n    pass\n", "utf-8")
        (wt / "src" / "iaso" / f"c{n}.py").write_text("FIXED = True\n", "utf-8")

    def runner(paths: list[str]) -> tuple[bool, str]:
        n = re.search(r"c(\d)\.py", paths[0]).group(1)
        with heavy_mod.heavy(iaso_repo, f"test run {n}"):
            count("run", "run_peak", 1)
            try:
                time.sleep(0.1)
                return (wts[f"hook-stop-{n}"] / "src" / "iaso" / f"c{n}.py").exists(), "ran"
            finally:
                count("run", "run_peak", -1)

    real = selfdebug.fix

    def scripted(c, case, **kw):
        n = case["id"][-1]
        return real(c, case, diagnoser=stage("d", diagnosis()),
                    fixer=lambda **k: (stage("f", {"test": f"tests/test_c{n}.py::test_c"},
                                             writes)(**k)),
                    reviewer=stage("r", OK), runner=runner,
                    judge=Judge(Meaning(True, "same", 0.9)), **kw)

    monkeypatch.setattr(selfdebug, "fix", scripted)
    worker.run_once(core, session)
    assert sorted(names) == ["d"] * 3 + ["f"] * 3 + ["r"] * 3   # a settled case is not run again
    assert sorted(c["state"] for c in debug.all_cases(iaso_repo)) == ["resolved"] * 3
    assert 1 < box["peak"] <= 2                  # two stage runs out at once, never three
    assert box["run_peak"] == 1                  # the test runs went one at a time
    assert len({p.resolve() for p in wts.values()}) == 3
    for cid, wt in wts.items():
        assert wt.parent == iaso_repo / ".iaso" / "wt" and wt.name.startswith("debug-")
        assert _git(iaso_repo, "rev-list", "--count", f"main..debug/{cid}").strip() == "1"
    assert set(seen_env) == {"selfdebug"}        # the hook guard stayed set in both threads
    assert os.environ.get("IASO_JOB") is None   # and was restored after the last one
    assert subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                          cwd=iaso_repo, capture_output=True, text=True
                          ).stdout == " M .iaso/config.yaml\n"     # only this test's limit
