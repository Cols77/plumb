"""V3: covering-test selection under R5 (spec 7.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, make_project, write

from plumb.api import open_core
from plumb.contracts import Target
from plumb.verify.select import select_tests
from plumb.verify.testmap import build_map


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo)
    write_record(repo, SR_TEXT)
    return repo


def _select(root: Path, changed, **kw):
    core = open_core(root)
    return select_tests(core, build_map(core), changed, **kw)


@pytest.mark.sr("SR-017")
def test_doc_only_selects_nothing(project: Path) -> None:
    sel = _select(project, ["docs/guide.md", "README.md"])
    assert sel.doc_only is True
    assert sel.nodes == ()
    assert sel.unknown_coverage == ()


@pytest.mark.sr("SR-017")
def test_priority_order_verified_by_literal_import(project: Path) -> None:
    write(project, "tests/test_uses_lonely.py",
          "from pkg.lonely import VALUE\n\n\ndef test_value():\n    assert VALUE\n")
    write(project, "tests/test_lonely.py", "def test_named():\n    assert True\n")
    core = open_core(project)
    core.add_link("SR-001", "implemented_by", Target(path="src/pkg/lonely.py"))
    core.add_link("SR-001", "verified_by", Target(test="tests/test_helper.py::test_twice"))
    sel = _select(project, ["src/pkg/lonely.py"])
    # the sr marker on test_add links it to SR-001 as a verified_by link does
    assert sel.nodes[:5] == ("tests/test_helper.py::test_twice", "tests/test_mod.py::test_add",
                             "tests/test_paths.py", "tests/test_uses_lonely.py",
                             "tests/test_lonely.py")
    assert [sel.reasons[n] for n in sel.nodes[:5]] == ["verified_by", "verified_by", "literal",
                                                       "import", "naming"]
    assert sel.unknown_coverage == ()


@pytest.mark.sr("SR-017")
def test_import_closure_nearest_first_and_changed_test_selects_itself(project: Path) -> None:
    sel = _select(project, ["src/pkg/mod.py", "tests/test_paths.py"])
    assert sel.nodes == ("tests/test_paths.py", "tests/test_mod.py", "tests/test_helper.py")
    assert all(sel.reasons[n] == "import" for n in sel.nodes)


@pytest.mark.sr("SR-017")
def test_infra_change_sets_full_pending_and_adds_nothing(project: Path) -> None:
    write(project, "tests/conftest.py", "")
    sel = _select(project, ["pyproject.toml", "tests/conftest.py"])
    assert sel.infra_changed == ("pyproject.toml", "tests/conftest.py")
    assert sel.nodes == ()


@pytest.mark.sr("SR-017")
def test_unknown_coverage_samples_nearest_bounded(project: Path) -> None:
    for i in range(12):
        write(project, f"tests/sub/test_s{i:02d}.py", "def test_x():\n    assert True\n")
    write(project, "src/sub/newmod.py", "X = 1\n")
    sel = _select(project, ["src/sub/newmod.py"])
    assert sel.unknown_coverage == ("src/sub/newmod.py",)
    assert len(sel.sampled) == 10
    assert sel.sampled[0] == "tests/sub/test_s00.py"
    assert all(n.startswith("tests/sub/") for n in sel.sampled)
    assert all(sel.reasons[n] == "sample" for n in sel.sampled)
    again = _select(project, ["src/sub/newmod.py"])
    assert again.sampled == sel.sampled


@pytest.mark.sr("SR-017")
def test_budget_defers_overflow(project: Path) -> None:
    durations = {"tests/test_mod.py::test_add": 4.0, "tests/test_mod.py::test_add_zero": 4.0,
                 "tests/test_helper.py::test_twice": 9.0}
    sel = _select(project, ["src/pkg/mod.py"], budget_s=10, durations=durations)
    assert sel.nodes == ("tests/test_mod.py",)
    assert sel.deferred == ("tests/test_helper.py",)
    assert sel.expected_s == 8.0


@pytest.mark.sr("SR-017")
def test_unknown_duration_counts_one_second(project: Path) -> None:
    for i in range(5):
        write(project, f"tests/test_m{i}.py", "import pkg.mod\n\n\ndef test_x():\n    pass\n")
    # the selection fills 65 % of the budget (verify.fill_fraction): 2.6 s of 4 s
    sel = _select(project, ["src/pkg/mod.py"], budget_s=4)
    assert len(sel.nodes) == 2
    assert sel.expected_s == 2.0
    assert len(sel.deferred) == 5


@pytest.mark.sr("SR-017")
def test_selection_fills_a_fraction_of_the_budget_scaled_by_observed_time(
        project: Path) -> None:
    """A run slower than its estimate must not fill the whole budget (hard limit 1.5x)."""
    for i in range(5):
        write(project, f"tests/test_m{i}.py", "import pkg.mod\n\n\ndef test_x():\n    pass\n")
    sel = _select(project, ["src/pkg/mod.py"], budget_s=10)
    assert len(sel.nodes) == 6 and sel.expected_s == 6.0
    slow = _select(project, ["src/pkg/mod.py"], budget_s=10, scale=2.0)
    assert len(slow.nodes) == 3 and slow.expected_s == 6.0


@pytest.mark.sr("SR-017")
def test_selection_never_contains_whole_suite_marker(project: Path) -> None:
    sel = _select(project, ["src/pkg/mod.py", "src/pkg/lonely.py", "pyproject.toml",
                            "docs/guide.md", "tests"])
    for node in (*sel.nodes, *sel.deferred):
        assert node not in ("", ".", "tests", "tests/")
        assert node.split("::", 1)[0].endswith(".py")


@pytest.mark.sr("SR-017")
def test_parametrized_durations_count_for_their_node() -> None:
    from plumb.verify.select import expected_duration

    def nodes_of(_: str) -> list[str]:
        return ["tests/t.py::test_p", "tests/t.py::test_q"]

    durations = {"tests/t.py::test_p[1]": 0.5, "tests/t.py::test_p[2]": 0.25,
                 "tests/t.py::test_q": 0.25}
    assert expected_duration("tests/t.py", nodes_of, durations, 1.0) == 1.0
    assert expected_duration("tests/t.py::test_p", nodes_of, durations, 1.0) == 0.75
    del durations["tests/t.py::test_q"]
    assert expected_duration("tests/t.py", nodes_of, durations, 1.0) == 1.75


@pytest.mark.sr("SR-017")
def test_verify_is_a_verify_api(project: Path) -> None:
    from plumb.contracts import VerifyAPI
    from plumb.verify import open_verify

    assert isinstance(open_verify(open_core(project)), VerifyAPI)
