"""H7: the Stop hook: covering tests, the three triggers and the summary (spec 6.4, 6.5)."""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb import approvals
from plumb.api import open_core
from plumb.contracts import FullPending, NodeEvidence
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-012")

NODE = "tests/test_a.py::test_a"
NODE2 = "tests/test_a.py::test_b"
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


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", "utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text("notes\n", "utf-8")
    (repo / "tests").mkdir(exist_ok=True)  # NODE and NODE2 exist, so their failures count
    (repo / "tests" / "test_a.py").write_text("def test_a(): pass\n\n\ndef test_b(): pass\n",
                                              "utf-8")
    from plumb.contracts import Target

    open_core(repo).add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


def start_turn(repo: Path, session: str = "s1", asked: dict | None = None) -> None:
    path = repo / ".plumb" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64,
                                "asked": asked or {}}), "utf-8")


def edit(repo: Path, rel: str, text: str, session: str = "s1") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    touched = repo / ".plumb" / "session" / session / "touched.txt"
    with touched.open("a", encoding="utf-8") as handle:
        handle.write(rel + "\n")


def run_stop(repo: Path, hook_input, *, active: bool = False, session: str = "s1",
             verify=None, **kwargs) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=session, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=verify,
                     unjudged=kwargs.pop("unjudged", None), **kwargs) == 0
    return out.getvalue()


def _block(out: str) -> str | None:
    if not out.strip():
        return None
    data = json.loads(out)
    return data["reason"] if data.get("decision") == "block" else None


def _summary(out: str) -> str:
    return json.loads(out)["systemMessage"] if out.strip() else ""


def fresh(*nodes: str, state: str = "fresh-pass", **kw) -> dict[str, NodeEvidence]:
    return {n: NodeEvidence(n, state, **kw) for n in nodes}


def test_blocks_once_when_covering_tests_not_fresh(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE, NODE2), evidence_map=fresh(NODE))
    reason = _block(run_stop(project, hook_input, verify=verify))
    # the command names this turn's paths, so other uncommitted work cannot crowd the
    # turn's own covering tests out of the budget
    assert reason == ("plumb: run 'plumb tests run --paths src/calc.py' (covering tests of "
                      "this turn, budget 15 s), then finish your reply.")
    assert verify.select_calls == [("src/calc.py",)]


def test_block_falls_back_to_changed_for_many_paths(project: Path, hook_input) -> None:
    start_turn(project)
    for i in range(9):
        edit(project, f"src/m{i}.py", f"X = {i}\n")
    verify = FakeVerify(nodes=(NODE,))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason.startswith("plumb: run 'plumb tests run --changed' (covering tests")


def test_block_quotes_paths_with_spaces(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/my calc.py", "X = 1\n")
    verify = FakeVerify(nodes=(NODE,))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert "plumb tests run --paths \"src/my calc.py\"" in reason


def _status(repo: Path) -> dict:
    return json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))


def test_no_block_when_stop_hook_active(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,))
    out = run_stop(project, hook_input, verify=verify, active=True)
    assert _block(out) is None
    assert _summary(out) == ""                      # nothing needs the owner: no text at all
    assert _status(project)["tests"] != "regression"


def test_the_status_card_is_the_status_lines_not_the_owners_text(project: Path,
                                                                  hook_input) -> None:
    """Slice 3 (SR-012, sp7-realign-sp8 C7): the status card and the summary lines left the
    owner's text; the status line shows them from status.json."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE, NODE2), deferred=("tests/test_z.py::test_z",),
                        evidence_map={**fresh(NODE), **fresh(NODE2, state="fresh-fail")},
                        pending=FullPending(True, ("tests/conftest.py changed",)))
    for card in ("full", "compact"):
        (project / ".plumb" / "config.yaml").write_text(f"present:\n  card: {card}\n", "utf-8")
        start_turn(project)
        edit(project, "src/calc.py", "def add(a, b):\n    return a + b\n")
        assert _summary(run_stop(project, hook_input, verify=verify)) == ""
        status = _status(project)
        assert status["deferred"] == 1 and status["full_pending"] is True
        assert status["full_pending_reasons"] == ["tests/conftest.py changed"]


def test_a_stale_link_is_counted_in_the_status_line(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a - b\n")
    summary = _summary(run_stop(project, hook_input, verify=FakeVerify()))
    assert "stale:" not in summary and "plumb: touched" not in summary
    assert _status(project)["stale_links"] == 1


def _stated(repo: Path) -> dict[str, bool]:
    data = json.loads((repo / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    return {r["id"]: r["shown"] for r in data["records"]}


def test_a_blocked_stop_shows_the_owner_nothing(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, ".plumb/requirements/SR-002.md", SR1.replace("SR-001", "SR-002"))
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    assert _block(run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,)))) is not None
    assert _stated(project) == {"SR-002": False}


def test_regression_blocks_with_owner_instruction(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a * b\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(
        NODE, state="fresh-fail", regression=True, last_run="run-2"))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason == (f"plumb: regression: {NODE} passed in an earlier run and now fails "
                      "(last run run-2). Tell the owner, with a read-back, and ask how to "
                      "proceed.")
    # asked once per failing run: the next stop does not block again
    start_turn(project, asked=json.loads((project / ".plumb" / "session" / "s1" /
                                          "turn.json").read_text("utf-8"))["asked"])
    out = run_stop(project, hook_input, verify=verify)
    assert _block(out) is None
    summary = _summary(out)
    # the owner gets a regression card (no requirement verifies it here: the test names it)
    assert summary.startswith(f"{NODE}\na test that passed before now fails: {NODE}")
    assert f"{NODE} passed in an earlier run and fails now (last run run-2)" in summary
    assert "  1. Fix the code so it passes again (recommended)" in summary
    assert "questions:" not in summary and "▸" not in summary


@pytest.mark.sr("SR-020")
def test_edited_test_regression_still_blocks(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "tests/test_a.py", "def test_a():\n    assert False\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(
        NODE, state="fresh-fail", regression=True, test_changed_since_pass=True,
        last_run="run-3"))
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason is not None
    assert "now fails (test source changed since the pass)" in reason


@pytest.mark.sr("SR-020")
def test_new_red_test_never_asks(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "tests/test_new.py", "def test_new():\n    assert False\n")
    node = "tests/test_new.py::test_new"
    verify = FakeVerify(nodes=(node,), evidence_map=fresh(node, state="fresh-fail"))
    out = run_stop(project, hook_input, verify=verify)
    assert _block(out) is None
    assert _summary(out) == ""                       # no card: a new red test asks nothing
    status = _status(project)                        # the status line: not yet passing
    assert status["regressions"] == [] and status["failing"] == [node]
    assert status["tests"] == "failing"


def test_doc_only_turn_prints_at_most_one_line(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "docs/notes.md", "more notes\n")
    verify = FakeVerify(nodes=(NODE,))
    out = run_stop(project, hook_input, verify=verify)
    assert _block(out) is None
    assert len(_summary(out).splitlines()) <= 2  # the status card and one line


def test_writes_stated_set(project: Path, hook_input) -> None:
    start_turn(project)
    text = SR1.replace("SR-001", "SR-002").replace("Adds numbers", "Subtracts")
    edit(project, ".plumb/requirements/SR-002.md", text)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    run_stop(project, hook_input, verify=FakeVerify(), active=True)
    stated = json.loads((project / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    index = open_core(project).index()
    assert stated["records"] == [{"id": "SR-002", "hash": index["SR-002"].hash,
                                  "shown": False}]    # no card draws it any more
    assert stated["session"] == "s1" and stated["reply_after_prompt"] == "sha256:" + "a" * 64


def test_no_change_turn_prints_nothing(project: Path, hook_input) -> None:
    start_turn(project)
    verify = FakeVerify(nodes=(NODE,))
    assert run_stop(project, hook_input, verify=verify) == ""
    assert verify.select_calls == []


def test_old_uncommitted_changes_are_not_this_turn(project: Path, hook_input) -> None:
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return 0\n", "utf-8")
    time.sleep(0.05)
    path = project / ".plumb" / "session" / "s1" / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() + 1, "asked": {}}), "utf-8")
    assert run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,))) == ""


def test_git_status_changes_count_without_touched(project: Path, hook_input) -> None:
    start_turn(project)
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return b + a\n", "utf-8")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(NODE))
    run_stop(project, hook_input, verify=verify)
    assert verify.select_calls == [("src/calc.py",)]


def test_verify_unavailable_degrades(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    out = run_stop(project, hook_input, verify=None)
    assert _block(out) is None
    assert _summary(out) == ""
    assert _status(project)["tests"] == "unknown"


def test_unjudged_fidelity_goes_to_the_status_line(project: Path, hook_input) -> None:
    start_turn(project)
    approvals.approve(open_core(project), ["SR-001"])
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    out = run_stop(project, hook_input, verify=FakeVerify(),
                   unjudged=lambda core, ids: tuple(i for i in ids or () if i == "SR-001"))
    assert _summary(out) == ""                       # no summary line: cards only
    assert _status(project)["fidelity_unjudged"] == ["SR-001"]


def test_writes_status_snapshot(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map=fresh(
        NODE, state="fresh-fail", regression=True, last_run="r"))
    run_stop(project, hook_input, verify=verify)
    data = json.loads((project / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["tests"] == "regression" and data["ask"] == 1


class _Clock:
    """A ``time`` stand-in for the hook deadline: frozen until a step advances it."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def __getattr__(self, name: str):
        return getattr(time, name)


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    from plumb.hosts.claude_code import hookio

    fake = _Clock()
    monkeypatch.setattr(hookio, "time", fake)
    return fake


class _SlowVerify(FakeVerify):
    """Covering selection that finishes after the stop hook's soft budget has passed."""

    clock: _Clock | None = None

    def select(self, changed, *, budget_s=None):
        result = super().select(changed, budget_s=budget_s)
        assert self.clock is not None
        self.clock.now += 5.0
        return result


def test_results_finished_past_the_budget_are_used(project: Path, hook_input,
                                                   clock: _Clock) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return int(a) + int(b)\n")
    edit(project, ".plumb/requirements/SR-001.md",
         SR1.replace("add returns the sum.", "add returns the integer sum."))
    verify = _SlowVerify(nodes=(NODE, NODE2), evidence_map=fresh(
        NODE2, state="fresh-fail", regression=True, last_run="r9"))
    verify.clock = clock
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason is not None
    assert "plumb: run 'plumb tests run --paths " in reason
    assert f"plumb: regression: {NODE2}" in reason
    stated = json.loads((project / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert "SR-001" in {r["id"] for r in stated["records"]}
    status = json.loads((project / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert status["tests"] == "regression"
    log = project / ".plumb" / "session" / "errors.log"
    assert not log.exists() or "budget exceeded" not in log.read_text("utf-8")


class _SlowCore:
    """A CoreAPI whose record states finish after the soft budget has passed."""

    def __init__(self, core, clock: _Clock) -> None:
        self._core, self._clock = core, clock

    def status(self, *args, **kwargs):
        result = self._core.status(*args, **kwargs)
        self._clock.now += 5.0
        return result

    def __getattr__(self, name: str):
        return getattr(self._core, name)


def test_a_step_starting_past_the_budget_is_skipped_and_reported(
        project: Path, hook_input, clock: _Clock, monkeypatch) -> None:
    import plumb.api

    real_open = plumb.api.open_core
    monkeypatch.setattr(plumb.api, "open_core", lambda root: _SlowCore(real_open(root), clock))
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return int(a) + int(b)\n")
    verify = FakeVerify(nodes=(NODE,))
    out = run_stop(project, hook_input, verify=verify)
    assert verify.select_calls == []  # the covering-tests step would start past the deadline
    reason = _block(out)
    assert reason is not None
    assert "plumb: check skipped (budget): covering tests" in reason
    status = json.loads((project / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert status["skipped"] == "covering tests"
    # the next turn: the cut selection still asks the agent for the
    # covering tests of the turn's code change (R5), then the summary names the skip
    start_turn(project, asked=json.loads(
        (project / ".plumb" / "session" / "s1" / "turn.json").read_text("utf-8"))["asked"])
    edit(project, "src/calc.py", "def add(a, b):\n    return int(b) + int(a)\n")
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert reason is not None and "plumb tests run --paths src/calc.py" in reason
    summary = _summary(run_stop(project, hook_input, verify=verify, active=True))
    assert _status(project)["skipped"] == "covering tests"     # the status line names it
    assert "check skipped" not in summary


class _CutVerify(FakeVerify):
    """Covering selection cut by the budget while it runs (a loaded machine)."""

    def select(self, changed, *, budget_s=None):
        from plumb.hosts.claude_code.hookio import BudgetExceeded

        raise BudgetExceeded("covering tests")


def test_skipped_covering_tests_are_named_in_the_status_line(project: Path, hook_input,
                                                             clock: _Clock,
                                                             monkeypatch) -> None:
    import plumb.api

    real_open = plumb.api.open_core
    monkeypatch.setattr(plumb.api, "open_core", lambda root: _SlowCore(real_open(root), clock))
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return int(a) + int(b)\n")
    out = run_stop(project, hook_input, active=True, verify=FakeVerify(nodes=(NODE,)))
    assert "questions: none" not in _summary(out)
    assert _status(project)["skipped"] == "covering tests"


def test_a_slow_git_status_is_reported_not_read_as_no_changes(project: Path, hook_input,
                                                              monkeypatch) -> None:
    """Under load `git status` can outlast its timeout: the stop hook says the change check
    was skipped instead of printing nothing, which would read as a turn without changes."""
    start_turn(project)
    # an edit made through a shell command: no touched list, only git sees it
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return a - -b\n", "utf-8")

    def slow_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git status", timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(stop.subprocess, "run", slow_run)
    summary = _summary(run_stop(project, hook_input, verify=FakeVerify()))
    assert summary == ""                                 # cards only: the status line says it
    assert _status(project)["skipped"] == "change detection (git status)"


def test_git_status_gets_most_of_the_remaining_budget() -> None:
    assert stop.GIT_TIMEOUT_S >= 1.0


# -- untraced changes: work no requirement owns (spec 6.4, R1) -------------------------


def _note(repo: Path, session: str = "s1") -> dict | None:
    path = repo / ".plumb" / "session" / session / "untraced.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else None


@pytest.mark.sr("SR-026")
def test_untraced_change_is_queued_for_the_agent(project: Path, hook_input) -> None:
    """SR-012 (cards only) leaves no summary line to name it to the owner in: the agent is
    told at the next prompt (SR-026 EX-1's "the summary names it" no longer holds)."""
    start_turn(project)
    edit(project, "src/mul.py", "def mul(a, b):\n    return a * b\n")
    out = run_stop(project, hook_input, verify=FakeVerify())
    assert _block(out) is None  # non-blocking (R1)
    assert "untraced" not in _summary(out)
    assert _note(project)["paths"] == ["src/mul.py"]


@pytest.mark.sr("SR-026")
def test_untraced_change_rides_along_an_existing_block(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/mul.py", "def mul(a, b):\n    return a * b\n")
    reason = _block(run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,))))
    lines = reason.splitlines()
    assert lines[0].startswith("plumb: run 'plumb tests run --paths src/mul.py'")
    assert any(line.startswith("plumb: untraced change: src/mul.py changed with no "
                               "requirement owning it. Read the change back") for line in lines)
    assert _note(project) is None  # already told in this turn


@pytest.mark.sr("SR-026")
def test_linked_change_is_not_untraced(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    out = run_stop(project, hook_input, verify=FakeVerify())
    assert "untraced" not in _summary(out)
    assert _note(project) is None


@pytest.mark.sr("SR-029")
def test_flat_layout_and_root_files_are_untraced_at_the_stop(project: Path,
                                                              hook_input) -> None:
    """No source_dirs configured: a flat package module and a root script are named."""
    start_turn(project)
    edit(project, "mypkg/power.py", "def power(a):\n    return a ** 2\n")
    edit(project, "tool.py", "print('tool')\n")
    out = run_stop(project, hook_input, verify=FakeVerify())
    assert _block(out) is None
    assert _note(project)["paths"] == ["mypkg/power.py", "tool.py"]
