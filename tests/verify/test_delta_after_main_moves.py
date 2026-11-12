"""SR-254 EX-22/EX-23 (owner, 2026-11-12, DEC-549): a branch's green full run still counts after
main moves: only the covering tests of what changed since run, once, on the merged tree, and
their pass counts as that tree's full run; shared test infrastructure still needs a full run."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from iaso.api import open_core
from iaso.boundary import fullrun
from iaso.verify import open_verify

pytestmark = pytest.mark.sr("SR-254")


@pytest.fixture
def green(repo: Path) -> Path:
    """A committed project with a green full run of its tree."""
    make_project(repo)
    commit_all(repo, "base")
    assert open_verify(open_core(repo)).run(full=True).ok
    return repo


def _plan(root: Path):
    core = open_core(root)
    verify = open_verify(core)
    return core, verify, fullrun.delta_plan(core, verify, fullrun.current_identity(core, verify))


def test_after_main_moves_only_the_covering_tests_run_and_count_as_the_full_run(
        green: Path) -> None:
    write(green, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")   # main moved
    commit_all(green, "merge main")
    core, verify, plan = _plan(green)
    assert fullrun.run_of_merged_tree(core, verify) is None              # no exact run yet
    assert plan is not None and plan[1] == ["src/pkg/mod.py"]
    result = fullrun.run_delta(core, verify, *plan)
    assert result.ok and "tests/test_paths.py::test_mentions" not in result.outcomes
    counted = fullrun.run_of_merged_tree(open_core(green), open_verify(open_core(green)))
    assert counted is not None and counted["extends"]["run_id"] == plan[0]["run_id"]


def test_a_change_to_shared_test_infrastructure_still_needs_a_full_run(green: Path) -> None:
    write(green, "pyproject.toml", (green / "pyproject.toml").read_text() + "\n# moved\n")
    commit_all(green, "merge main")
    assert _plan(green)[2] is None


def test_a_covering_run_of_another_tree_does_not_count(green: Path) -> None:
    write(green, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    commit_all(green, "merge main")
    core, verify, plan = _plan(green)
    assert fullrun.run_delta(core, verify, *plan).ok
    write(green, "src/pkg/helper.py", (green / "src/pkg/helper.py").read_text() + "# more\n")
    commit_all(green, "main moved again")                                # not run on this tree
    assert fullrun.run_of_merged_tree(open_core(green), open_verify(open_core(green))) is None


def test_the_merge_checks_run_step_takes_the_covering_run_not_the_full_suite(
        green: Path) -> None:
    write(green, "src/pkg/mod.py", "def add(a, b):\n    return b + a\n")
    commit_all(green, "merge main")
    core = open_core(green)

    def no_full_run(_core):
        raise AssertionError("the full suite ran")

    out = fullrun.full_run(core, open_verify(core), pending=True, reasons=["main moved"],
                           unverified=False, waived=False, run_full=True, runner=no_full_run)
    assert out["ran"] and out["delta"] and out["verdict"] == "passed", out
