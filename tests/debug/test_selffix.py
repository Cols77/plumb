"""SR-326: a debug case in iaso's own repository becomes a fix on a branch of its own: a
worktree, a fixer that names a failing test, verification (the test fails without the source
change and passes with it, covering tests, nothing stale, the judge keeps every meaning), a
commit with the requirement trailer, or after three rounds a defect report. The fixer is
scripted and edits a scratch iaso-shaped repository; the runner and the judge are stubbed;
git is real."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from iaso import debug, selfdebug, stale
from iaso import heavy as heavy_mod
from iaso.api import open_core
from iaso.config import Config
from iaso.contracts import Target
from iaso.understand import jobs, judge, repin
from iaso.understand import selfdebug as kind
from iaso.understand.repin import Meaning

pytestmark = pytest.mark.sr("SR-326")

SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum{suffix}.
---
"""
DEC1 = """---
id: DEC-001
title: Does add round its result?
question: Does add round its result?
chosen: 'No: add returns the exact sum'
alternatives:
- Round to two decimals
---
"""
CASE = "hook-stop-1"
BRANCH = "debug/hook-stop-1"
TEST = "tests/test_calc.py::test_add"


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8")
    return done.stdout


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch) -> None:
    monkeypatch.setattr(repin, "open_jev_tier", lambda core: None)
    monkeypatch.setattr(repin, "open_diagnoser", lambda core: None)


@pytest.fixture
def iaso_repo(repo: Path, write_record) -> Path:
    """A iaso-shaped repository with a defect in src/iaso/calc.py, a requirement whose code
    link names it and a decision pinned to the requirement; one open debug case."""
    (repo / "pyproject.toml").write_text('[project]\nname = "iaso"\n', "utf-8")
    (repo / "src" / "iaso").mkdir(parents=True)
    (repo / "src" / "iaso" / "__init__.py").write_text("", "utf-8")
    (repo / "src" / "iaso" / "calc.py").write_text(
        "def add(a, b):\n    return a - b  # BUG\n", "utf-8")
    write_record(repo, SR1.format(suffix=""))
    write_record(repo, DEC1)
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/iaso/calc.py"))
    core.add_link("DEC-001", "decides", Target(record="SR-001"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    debug.open_case(repo, id=CASE, kind="hook-error", target="stop",
                    detail="ValueError: add is wrong (SR-001)")
    return repo


class Fixer:
    """Scripted: round n runs ``steps[n-1]`` on the worktree and names the test."""

    def __init__(self, *steps) -> None:
        self.steps, self.models, self.wt = list(steps), [], None

    def __call__(self, *, round, case, evidence, worktree, model, previous, **_):
        self.models.append(model)
        self.wt = worktree
        self.evidence, self.previous = evidence, previous
        self.steps[min(round, len(self.steps)) - 1](worktree)
        return {"test": TEST, "files": []}


def fixes_add(wt: Path) -> None:
    (wt / "tests").mkdir(exist_ok=True)
    (wt / "tests" / "test_calc.py").write_text(
        "from iaso.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", "utf-8")
    (wt / "src" / "iaso" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n", "utf-8")


def fixes_nothing(wt: Path) -> None:
    (wt / "tests").mkdir(exist_ok=True)
    (wt / "tests" / "test_calc.py").write_text("def test_add():\n    assert False\n", "utf-8")


class Runner:
    """Every run passes unless the worktree's calc.py still holds the defect."""

    def __init__(self, fixer: Fixer) -> None:
        self.fixer, self.calls = fixer, []

    def __call__(self, paths):
        ok = "BUG" not in (self.fixer.wt / "src" / "iaso" / "calc.py").read_text("utf-8")
        self.calls.append((list(paths), ok))
        return ok, "passed" if ok else "failed: the defect"


class Judge:
    def __init__(self, answer: Meaning) -> None:
        self.answer, self.asked = answer, []

    def same_meaning(self, **shown):
        self.asked.append(shown)
        return self.answer


def _fix(repo: Path, fixer: Fixer, answer: Meaning, rounds: int = 3):
    core = open_core(repo)
    case = next(c for c in debug.open_cases(repo) if c["id"] == CASE)
    runner, sonnet = Runner(fixer), Judge(answer)
    from debug.staged import ok_stages  # SR-388: the diagnosis and the review, scripted

    out = selfdebug.fix(core, case, rounds=rounds, fixer=fixer, runner=runner, judge=sonnet,
                        **ok_stages())
    return out, runner, sonnet


def _state(repo: Path) -> str:
    return next(c["state"] for c in debug.all_cases(repo) if c["id"] == CASE)


def test_ex1_a_planted_defect_ends_as_a_branch_with_its_failing_then_passing_test(
        iaso_repo: Path) -> None:
    fixer = Fixer(fixes_add)
    out, runner, sonnet = _fix(iaso_repo, fixer, Meaning(True, "wording only", 0.9))
    assert out.state == "fixed" and out.branch == BRANCH, out.detail
    assert _git(iaso_repo, "show", f"{BRANCH}:tests/test_calc.py").count("def test_add") == 1
    assert "return a + b" in _git(iaso_repo, "show", f"{BRANCH}:src/iaso/calc.py")
    assert "SR: SR-001" in _git(iaso_repo, "log", "-1", "--format=%B", BRANCH)
    # the test failed without the source change, then passed with it; the covering tests passed
    assert [c for c in runner.calls if c[0] == [TEST]] == [([TEST], True), ([TEST], False)]
    assert (["src/iaso/calc.py"], True) in runner.calls
    wt_core = open_core(fixer.wt)
    assert [s.link.id for s in wt_core.link_states() if s.state != "current"] == []
    assert len(sonnet.asked) == 1
    assert [e.payload["case"] for e in open_core(iaso_repo).log_read(
        "events", ["selfdebug-review"])] == [CASE]
    assert _state(iaso_repo) == "resolved"
    assert next(c for c in debug.all_cases(iaso_repo) if c["id"] == CASE)["branch"] == BRANCH
    assert "SR-001" in fixer.evidence["records"] and fixer.models == ["sonnet"]


def test_ex2_a_stale_link_is_repinned_when_the_meaning_holds_else_nothing_is_committed(
        iaso_repo: Path) -> None:
    fixer = Fixer(fixes_add)
    out, _, _ = _fix(iaso_repo, fixer, Meaning(False, "add now adds"), rounds=1)
    assert out.state == "reported" and "SR-001#0" in out.detail
    assert _state(iaso_repo) == "open"
    assert _git(iaso_repo, "rev-list", "--count", f"main..{BRANCH}").strip() == "0"
    out, _, _ = _fix(iaso_repo, fixer, Meaning(True, "the same meaning"))
    assert out.state == "fixed" and _state(iaso_repo) == "resolved"
    assert _git(iaso_repo, "rev-list", "--count", f"main..{BRANCH}").strip() == "1"
    assert all(s.state == "current" for s in open_core(fixer.wt).link_states(["SR-001"]))


def test_ex3_a_changed_meaning_is_one_owner_question_and_no_commit(
        iaso_repo: Path, write_record) -> None:
    def rewords(wt: Path) -> None:
        fixes_add(wt)
        (wt / ".iaso" / "requirements" / "SR-001.md").write_text(
            SR1.format(suffix=", rounded to two decimals"), "utf-8")

    fixer = Fixer(rewords)
    out, _, _ = _fix(iaso_repo, fixer, Meaning(False, "the sum is now rounded"))
    assert out.state == "owner" and _state(iaso_repo) == "open"
    assert _git(iaso_repo, "rev-list", "--count", f"main..{BRANCH}").strip() == "0"
    asked = judge.questions_path(iaso_repo, stale.current_session(iaso_repo))
    text = asked.read_text("utf-8")
    assert text.count('"key"') == 1 and "rounded to two decimals" in text
    assert "SR-001" not in text.split('"records"')[0]


def test_ex4_three_failed_rounds_end_as_a_defect_report_and_ask_nothing(
        iaso_repo: Path) -> None:
    fixer = Fixer(fixes_nothing)
    out, _, _ = _fix(iaso_repo, fixer, Meaning(True, "same"))
    assert out.state == "reported" and len(out.rounds) == 3
    assert fixer.models == ["sonnet", "opus", "fable"] and len(fixer.previous) == 2
    (row,) = [c for c in debug.open_cases(iaso_repo) if c["id"] == CASE]
    assert "round 1" in row["report"] and "round 3" in row["report"]
    assert "Missing:" in row["report"] and "Nothing was committed" in row["report"]
    assert _git(iaso_repo, "rev-list", "--count", f"main..{BRANCH}").strip() == "0"
    assert not judge.questions_path(iaso_repo, stale.current_session(iaso_repo)).exists()


def test_ex5_no_judge_holds_the_workflow_says_so_once_and_commits_nothing(
        iaso_repo: Path) -> None:
    fixer = Fixer(fixes_add)
    out, _, _ = _fix(iaso_repo, fixer, Meaning(None, "no key", 0.0, unreachable=True))
    assert out.state == "held" and "waiting" in out.line and len(fixer.models) == 1
    assert _state(iaso_repo) == "open"
    assert _git(iaso_repo, "rev-list", "--count", f"main..{BRANCH}").strip() == "0"
    again, _, _ = _fix(iaso_repo, Fixer(fixes_add), Meaning(None, "no key", 0.0))
    assert again.state == "held" and again.line == ""


def test_ex6_the_main_checkout_is_not_written_and_not_merged(iaso_repo: Path) -> None:
    head = _git(iaso_repo, "rev-parse", "HEAD")
    calc = (iaso_repo / "src" / "iaso" / "calc.py").read_text("utf-8")
    out, _, _ = _fix(iaso_repo, Fixer(fixes_add), Meaning(True, "same"))
    assert out.state == "fixed"
    assert _git(iaso_repo, "rev-parse", "HEAD") == head
    assert _git(iaso_repo, "rev-parse", "main") == head
    assert _git(iaso_repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert (iaso_repo / "src" / "iaso" / "calc.py").read_text("utf-8") == calc
    assert not (iaso_repo / "tests" / "test_calc.py").exists()


def test_the_case_is_queued_as_a_background_job_only_in_iasos_own_repository(
        iaso_repo: Path, tmp_path: Path) -> None:
    core = open_core(iaso_repo)
    job = kind.build(core, stale.current_session(iaso_repo), case=CASE)
    assert selfdebug.applies(core) is None
    assert jobs.job_path(iaso_repo, job.session, job.id).exists()
    assert kind.recompute(core, job) == {"case": CASE}
    assert "not iaso's own" in selfdebug.applies(SimpleNamespace(root=tmp_path, config=Config()))


def test_the_background_run_waits_for_the_heavy_lock(repo: Path, monkeypatch) -> None:
    """One heavy job at a time across sessions: a run waits while another holds the lock,
    takes it, and leaves none behind."""
    import threading

    monkeypatch.setattr(heavy_mod, "HEAVY_WAIT_S", 0.01)
    lock = repo / ".git" / "iaso-heavy.lock"
    lock.write_text("another session: pytest\n", encoding="utf-8")
    seen: list[str] = []

    def job() -> None:
        with selfdebug.heavy(repo, "selfdebug x: pytest"):
            seen.append(lock.read_text(encoding="utf-8").splitlines()[0])

    t = threading.Thread(target=job)
    t.start()
    t.join(0.2)
    assert t.is_alive() and not seen          # still waiting on the other session
    lock.unlink()
    t.join(5)
    assert seen == ["selfdebug x: pytest"] and not lock.exists()


def test_the_background_job_runs_the_fix(iaso_repo: Path, monkeypatch) -> None:
    got: dict = {}
    monkeypatch.setattr(selfdebug, "fix", lambda core, case, **kw: got.update(kw)
                        or selfdebug.Outcome("fixed", BRANCH, "ok"))
    job = kind.build(open_core(iaso_repo), "s", case=CASE)
    kind.cascade(open_core(iaso_repo), job)
    assert got == {"guard": None}     # SR-388: the worker's guard, none outside the worker


def _commit_file(root: Path, name: str) -> None:
    (root / name).write_text(name, "utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-q", "-m", name)


def _boom(**kw):
    raise AssertionError("a landed case runs no fixer")


def test_ex7_a_branch_with_its_own_commit_in_head_is_landed_and_the_case_resolved(
        iaso_repo: Path) -> None:
    _git(iaso_repo, "checkout", "-q", "-b", BRANCH)
    _commit_file(iaso_repo, "fix.txt")
    _git(iaso_repo, "checkout", "-q", "main")
    _git(iaso_repo, "merge", "-q", "--ff-only", BRANCH)
    core = open_core(iaso_repo)
    case = next(c for c in debug.open_cases(iaso_repo) if c["id"] == CASE)
    out = selfdebug.fix(core, case, fixer=_boom, runner=_boom, judge=_boom)
    assert out.state == "landed" and out.branch == BRANCH
    assert out.detail == f"already landed: {BRANCH}"
    assert _state(iaso_repo) == "resolved"
    assert not (iaso_repo / ".iaso" / "wt" / "debug-hook-stop-1").exists()
    assert _git(iaso_repo, "rev-parse", "--verify", BRANCH)       # merged branches are kept


def test_ex7_a_branch_without_its_own_commit_or_not_in_head_is_not_landed(
        iaso_repo: Path) -> None:
    assert not selfdebug.landed(iaso_repo, BRANCH)                 # no such branch
    _git(iaso_repo, "branch", BRANCH)                              # created, never fixed
    _commit_file(iaso_repo, "later.txt")                           # main moves on
    assert not selfdebug.landed(iaso_repo, BRANCH)
    _git(iaso_repo, "checkout", "-q", BRANCH)
    _commit_file(iaso_repo, "fix.txt")                             # its own commit, unmerged
    _git(iaso_repo, "checkout", "-q", "main")
    assert not selfdebug.landed(iaso_repo, BRANCH)
    _git(iaso_repo, "merge", "-q", "--no-edit", BRANCH)
    assert selfdebug.landed(iaso_repo, BRANCH)


def test_ex7_a_branch_without_a_reflog_is_not_landed(iaso_repo: Path) -> None:
    _git(iaso_repo, "checkout", "-q", "-b", BRANCH)
    _commit_file(iaso_repo, "fix.txt")
    _git(iaso_repo, "checkout", "-q", "main")
    _git(iaso_repo, "merge", "-q", "--ff-only", BRANCH)
    assert selfdebug.landed(iaso_repo, BRANCH)
    (iaso_repo / ".git" / "logs" / "refs" / "heads" / "debug" / "hook-stop-1").unlink()
    assert not selfdebug.landed(iaso_repo, BRANCH)


def test_ex8_a_branch_checked_out_elsewhere_is_reused_and_brought_to_head_when_unfixed(
        iaso_repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    _git(iaso_repo, "worktree", "add", "-q", "-b", BRANCH, str(other))
    _commit_file(iaso_repo, "later.txt")                           # main moves on
    wt, branch = selfdebug._worktree(iaso_repo, CASE)
    assert wt == other and branch == BRANCH
    assert _git(other, "rev-parse", "HEAD") == _git(iaso_repo, "rev-parse", "HEAD")
    assert not selfdebug.landed(iaso_repo, BRANCH)                 # moving forward is no fix
    assert not (iaso_repo / ".iaso" / "wt" / "debug-hook-stop-1").exists()


def test_ex8_a_branch_with_its_own_commit_or_a_dirty_worktree_is_used_as_it_is(
        iaso_repo: Path, tmp_path: Path) -> None:
    dirty, fixed = tmp_path / "dirty", tmp_path / "fixed"
    _git(iaso_repo, "worktree", "add", "-q", "-b", BRANCH, str(dirty))
    (dirty / "README.md").write_text("edited\n", "utf-8")
    _commit_file(iaso_repo, "later.txt")
    before = _git(dirty, "rev-parse", "HEAD")
    assert selfdebug._worktree(iaso_repo, CASE)[0] == dirty
    assert _git(dirty, "rev-parse", "HEAD") == before
    _git(iaso_repo, "worktree", "add", "-q", "-b", "debug/other-1", str(fixed))
    _commit_file(fixed, "fix.txt")
    tip = _git(fixed, "rev-parse", "HEAD")
    assert selfdebug._worktree(iaso_repo, "other-1")[0] == fixed
    assert _git(fixed, "rev-parse", "HEAD") == tip


def test_an_environment_error_is_no_round_no_report_and_leaves_no_work_copy(
        iaso_repo: Path) -> None:
    """report-63c3de43: a usage limit stops the run at once; the case stays open."""
    def limit(wt: Path) -> None:
        raise RuntimeError("run: You've hit your 5-hour limit · resets 1:10pm")

    out, _, _ = _fix(iaso_repo, Fixer(limit), Meaning(True, "same"))
    assert out.state == "waiting" and out.rounds == []
    row = next(c for c in debug.open_cases(iaso_repo) if c["id"] == CASE)
    assert "report" not in row
    assert not (iaso_repo / ".iaso" / "wt" / "debug-hook-stop-1").exists()
