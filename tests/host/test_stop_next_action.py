"""SR-373: a turn's end gives the agent exactly one next action; the owner one plain line only
when something needs them (SR-375: the rest goes to the background worker)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fakes import FakeVerify, agent_notes
from test_stop_stale import (  # noqa: F401 - the autouse fixture holds unresolved drift
    NODE,
    SR1,
    _block,
    _summary,
    _verify,
    edit,
    judge_reachable_tests_fail,
    run_stop,
    start_turn,
)

from plumb import approvals
from plumb.api import open_core
from plumb.contracts import NodeEvidence, Target

pytestmark = pytest.mark.sr("SR-373")

CODE = "def add(a, b):\n    return a + b\n"
CHANGED = "def add(a, b):\n    return b + a\n"


def _git(root: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    core.add_link("SR-001", "verified_by", Target(test=NODE))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    return repo


def _regressing() -> FakeVerify:
    return FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(
        NODE, "fresh-fail", regression=True, last_run="run-2")})


def test_ex1_covering_tests_without_a_fresh_run_are_the_one_action(project: Path,
                                                                    hook_input) -> None:
    start_turn(project)
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()   # no hold
    edit(project, "src/calc.py", CHANGED)
    reason = _block(run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,))))
    assert reason is not None and reason.splitlines() == [
        "plumb: run 'plumb tests run --paths src/calc.py' (covering tests of this turn, "
        "budget 60 s), then finish your reply."]
    # told once: the stop after the block says nothing more
    assert run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,)), active=True) == ""


def test_ex2_a_file_no_requirement_owns_is_to_be_proposed(project: Path, hook_input) -> None:
    start_turn(project)
    edit(project, "src/mul.py", "def mul(a, b):\n    return a * b\n")
    out = run_stop(project, hook_input, verify=_verify())
    assert _block(out) is None                 # never a block (R1)
    note = json.loads((project / ".plumb/session/s1/untraced.json").read_text("utf-8"))
    assert note["paths"] == ["src/mul.py"]     # the next prompt tells the agent to propose one
    from test_stop_stale import _prompt

    told = _prompt(project, hook_input)
    assert "src/mul.py" in told and "untraced change" in told


def test_ex3_three_links_moved_are_to_be_repinned_or_relinked(project: Path, hook_input,
                                                               write_record) -> None:
    for n in (2, 3):
        write_record(project, SR1.replace("SR-001", f"SR-00{n}"))
    core = open_core(project)
    for n in (2, 3):
        core.add_link(f"SR-00{n}", "implemented_by", Target(path="src/calc.py"))
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "two more owners")
    start_turn(project)
    edit(project, "src/calc.py", CHANGED)
    reason = _block(run_stop(project, hook_input, verify=_verify()))
    assert reason is not None
    for n in (1, 2, 3):
        assert f"SR-00{n}'s link to src/calc.py is stale and unresolved" in reason
    assert "plumb repin --after-tests" in reason
    assert "plumb tests run" not in reason


def test_ex4_a_turn_that_edited_nothing_prints_nothing(project: Path, hook_input) -> None:
    status = project / ".plumb" / "session" / "status.json"
    start_turn(project)
    before = status.read_text("utf-8") if status.exists() else None
    assert run_stop(project, hook_input, verify=_verify()) == ""
    assert (status.read_text("utf-8") if status.exists() else None) == before


def test_ex5_a_regression_on_confirmed_behaviour_names_it_to_the_owner(project: Path,
                                                                        hook_input) -> None:
    approvals.approve(open_core(project), ["SR-001"])
    start_turn(project)
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()
    edit(project, "src/calc.py", CHANGED)
    out = run_stop(project, hook_input, verify=_regressing())
    reason = _block(out)
    assert reason is not None and reason.startswith(f"plumb: regression: {NODE} passed")
    assert "plumb tests run" not in reason      # one action: the regression
    assert _summary(out) == "plumb: regression: 'Adds numbers' worked before and now fails"


def test_ex6_inside_an_intent_loop_the_owner_sees_nothing(project: Path, hook_input) -> None:
    from plumb.understand import cmd_intent

    approvals.approve(open_core(project), ["SR-001"])
    path = cmd_intent.open_loop(project, "s1", "sha256:" + "b" * 64)
    start_turn(project)
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()
    edit(project, "src/calc.py", CHANGED)
    out = run_stop(project, hook_input, verify=_regressing())
    assert _block(out) is not None              # the agent still gets its action
    assert _summary(out) == ""                  # the owner: nothing printed
    assert json.loads(path.read_text("utf-8"))["step"] != "proven"   # the band's step


def test_ex7_an_action_already_given_is_not_repeated(project: Path, hook_input) -> None:
    start_turn(project)
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()
    edit(project, "src/calc.py", CHANGED)
    assert _block(run_stop(project, hook_input, verify=_regressing())) is not None
    start_turn(project, turn_id="turn-2")       # a new turn, the same failing run
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()
    edit(project, "src/calc.py", CHANGED + "\n")
    out = run_stop(project, hook_input, verify=FakeVerify(nodes=(NODE,), evidence_map={
        NODE: NodeEvidence(NODE, "fresh-fail", regression=True, last_run="run-2")}))
    reason = _block(out)
    assert reason is None or "regression" not in reason


def test_ex8_past_the_budget_the_next_action_comes_now_and_the_rest_later(
        project: Path, hook_input, monkeypatch) -> None:
    from plumb.understand import summary

    (project / ".plumb" / "config.yaml").write_text("hooks:\n  budget_ms: {stop: 0}\n",
                                                    encoding="utf-8")
    monkeypatch.setattr(summary, "_confirmations",
                        lambda core, turn, told=None: ("Adds numbers: you said ok",))
    start_turn(project)
    (project / ".plumb" / "session" / "s1" / "stale_baseline.json").unlink()
    edit(project, "src/calc.py", CHANGED)
    verify = FakeVerify(nodes=(NODE,))
    began = time.monotonic()
    reason = _block(run_stop(project, hook_input, verify=verify))
    assert time.monotonic() - began < 10
    assert verify.select_calls == []            # the selection would start past the budget
    assert reason is not None and "plumb tests run --paths src/calc.py" in reason
    queued = project / ".plumb" / "session" / "s1" / summary.AFTER_STOP
    assert queued.is_file()                     # the rest waits for the background worker
    summary.after_stop(open_core(project), "s1")  # what the worker runs first
    assert not queued.exists()
    assert "Adds numbers: you said ok" in agent_notes(project)   # the next prompt delivers it
