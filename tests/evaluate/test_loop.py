"""SR-348 EX-3..EX-7: the evaluate, debug, merge loop, with doubles for run, fix and merge."""

import subprocess
from types import SimpleNamespace as NS

import pytest

from plumb.evaluate import loop

ISSUE = {"command": "plumb x", "expected": "a", "got": "b"}


@pytest.fixture(autouse=True)
def _doubles(monkeypatch):
    from plumb.evaluate import issues
    monkeypatch.setattr("plumb.api.open_core", lambda root: object())
    monkeypatch.setattr("plumb.debug.all_cases", lambda root: [])
    monkeypatch.setattr(issues, "open_cases", lambda root, found: ["eval-1"] * bool(found))


def _runs(*issue_lists):
    calls = []

    def run(root, task, *, model, **kw):
        calls.append(model)
        print(f"line {len(calls)}")
        return NS(issues=issue_lists[len(calls) - 1])
    return run, calls


def _fix(state, branch="debug/eval-1", detail="d"):
    return lambda core, case: NS(state=state, branch=branch, detail=detail)


@pytest.mark.sr("SR-348")
def test_stops_when_a_run_files_no_issue(tmp_path, capsys):
    run, calls = _runs([ISSUE], [])
    assert loop.run_loop(tmp_path, None, model="m", rounds=3, run=run, fix=_fix("fixed"),
                         merge=lambda r, b: "") == 0
    assert len(calls) == 2 and "stopped: the run filed no issue" in capsys.readouterr().out


@pytest.mark.sr("SR-348")
def test_owner_decision_stops_the_loop(tmp_path, capsys):
    run, calls = _runs([ISSUE], [ISSUE])
    assert loop.run_loop(tmp_path, None, model="m", rounds=3, run=run,
                         fix=_fix("owner", detail="which?")) == 1
    assert len(calls) == 1 and "stopped: eval-1 waits for the owner (which?)" in \
        capsys.readouterr().out


@pytest.mark.sr("SR-348")
def test_fixed_and_merged_runs_again_and_merge_gets_the_branch(tmp_path, capsys):
    run, calls = _runs([ISSUE], [])
    merged = []
    assert loop.run_loop(tmp_path, None, model="m", rounds=2, run=run, fix=_fix("fixed"),
                         merge=lambda r, b: merged.append(b) or "") == 0
    out = capsys.readouterr().out
    assert merged == ["debug/eval-1"] and len(calls) == 2
    assert out.index("line 1") < out.index("merged debug/eval-1") < out.index("line 2")


@pytest.mark.sr("SR-348")
def test_held_merge_stops_with_the_reason(tmp_path, capsys):
    run, calls = _runs([ISSUE], [ISSUE])
    assert loop.run_loop(tmp_path, None, model="m", rounds=2, run=run, fix=_fix("fixed"),
                         merge=lambda r, b: "SR-1 is unconfirmed") == 1
    assert len(calls) == 1 and "is held: SR-1 is unconfirmed" in capsys.readouterr().out


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                    *args], check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "user.email", "t@t")
    (tmp_path / "f.txt").write_text("base\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _branch(repo, name, text):
    _git(repo, "checkout", "-qb", name)
    (repo / "f.txt").write_text(text)
    _git(repo, "commit", "-qam", name)
    _git(repo, "checkout", "-q", "main")


@pytest.mark.sr("SR-348")
def test_merge_branch_merges_clean(tmp_path):
    repo = _repo(tmp_path)
    _branch(repo, "feat", "feat\n")
    assert loop.merge_branch(repo, "feat") == ""
    assert (repo / "f.txt").read_text() == "feat\n"


@pytest.mark.sr("SR-348")
def test_merge_branch_conflict_returns_reason_and_leaves_tree_clean(tmp_path):
    repo = _repo(tmp_path)
    _branch(repo, "feat", "feat\n")
    (repo / "f.txt").write_text("main\n")
    _git(repo, "commit", "-qam", "main change")
    assert loop.merge_branch(repo, "feat")
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
    assert status == "" and (repo / "f.txt").read_text() == "main\n"
