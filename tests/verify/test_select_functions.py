"""HB4 and HB6: selection by the functions a change touched (SR-110)."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, make_project, write

from plumb.api import open_core
from plumb.contracts import Target
from plumb.verify import open_verify
from plumb.verify.funcmap import FuncMap
from plumb.verify.select import select_tests
from plumb.verify.testmap import build_map

CORE = "src/pkg/core.py"
ENV = "env-1"
CORE_TEXT = "def alpha(x):\n    return x + 1\n\n\ndef beta(x):\n    return x * 2\n"


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo)
    write_record(repo, SR_TEXT)
    write(repo, CORE, CORE_TEXT)
    # twelve tests that execute alpha, thirty files that merely import the module
    write(repo, "tests/test_exec.py",
          "from pkg.core import alpha\n\n\n" + "\n\n".join(
              f"def test_alpha_{i:02d}():\n    assert alpha({i}) == {i + 1}" for i in range(12))
          + "\n")
    for i in range(30):
        write(repo, f"tests/test_imports_{i:02d}.py",
              "import pkg.core\n\n\ndef test_present():\n    assert pkg.core\n")
    return repo


def _record(core, executed: dict[str, list[str]], env: str = ENV) -> FuncMap:
    fm = FuncMap.open(core)
    fm.register_file(CORE)
    for node, funcs in executed.items():
        fm.record_test(node, node.split("::")[0], "digest", env, {(CORE, f) for f in funcs})
    fm.commit()
    return fm


def _select(root: Path, fm: FuncMap | None, changed, **kw):
    core = open_core(root)
    kw.setdefault("budget_s", 1000)
    return select_tests(core, build_map(core), changed, funcmap=fm, env_key=ENV, **kw)


EXEC_NODES = [f"tests/test_exec.py::test_alpha_{i:02d}" for i in range(12)]
IMPORTERS = {f"tests/test_imports_{i:02d}.py::test_present": [] for i in range(30)}


@pytest.mark.sr("SR-255")
def test_ex1_twelve_executing_tests_not_the_import_closure(project: Path) -> None:
    core = open_core(project)
    core.add_link("SR-001", "implemented_by", Target(path=CORE))
    core.add_link("SR-001", "verified_by", Target(test="tests/test_helper.py::test_twice"))
    fm = _record(core, {n: ["alpha"] for n in EXEC_NODES} | IMPORTERS)
    write(project, CORE, CORE_TEXT.replace("x + 1", "1 + x"))
    sel = _select(project, fm, [CORE])
    assert set(sel.nodes) == set(EXEC_NODES) | {"tests/test_helper.py::test_twice",
                                                "tests/test_mod.py::test_add"}
    assert all(sel.reasons[n] == "executed" for n in EXEC_NODES)
    assert sel.reasons["tests/test_helper.py::test_twice"] == "verified_by"
    assert sel.unrecorded == ()
    assert not any("test_imports" in n for n in sel.nodes)


@pytest.mark.sr("SR-255")
def test_ex2_new_function_falls_back_to_closure_and_says_so(project: Path) -> None:
    core = open_core(project)
    fm = _record(core, {n: ["alpha"] for n in EXEC_NODES})
    write(project, CORE, CORE_TEXT + "\n\ndef gamma(x):\n    return x - 1\n")
    sel = _select(project, fm, [CORE])
    assert sel.unrecorded == (f"{CORE}::gamma",)
    assert any("no recorded test executes gamma" in note for note in sel.notes)
    assert sel.reasons["tests/test_imports_07.py"] == "import"  # the closure of the file
    assert sel.unknown_coverage == ()


@pytest.mark.sr("SR-255")
def test_requirement_linked_tests_added(project: Path) -> None:
    core = open_core(project)
    core.add_link("SR-001", "implemented_by", Target(path=CORE))
    fm = _record(core, {EXEC_NODES[0]: ["beta"]} | {n: [] for n in EXEC_NODES[1:]}
                 | IMPORTERS)
    write(project, CORE, CORE_TEXT.replace("x * 2", "2 * x"))
    sel = _select(project, fm, [CORE])
    assert sel.nodes[0] == EXEC_NODES[0]
    assert sel.reasons["tests/test_mod.py::test_add"] == "verified_by"
    assert set(sel.nodes) == {EXEC_NODES[0], "tests/test_mod.py::test_add"}


@pytest.mark.sr("SR-255")
def test_nothing_recorded_never_runs_everything(project: Path) -> None:
    core = open_core(project)
    empty = FuncMap.open(core)
    write(project, "src/pkg/orphan.py", "def lone():\n    return 1\n")
    sel = _select(project, empty, ["src/pkg/orphan.py"])
    tests = build_map(core).test_files
    assert len(sel.nodes) <= core.config.verify.sample_size < len(tests)
    assert sel.unknown_coverage == ("src/pkg/orphan.py",)
    # recorded file, a changed function nobody executed, no importer: sample, never all
    fm = _record(core, {EXEC_NODES[0]: ["alpha"]})
    write(project, CORE, CORE_TEXT.replace("x * 2", "2 * x"))
    sel = _select(project, fm, [CORE])
    assert sel.unrecorded == (f"{CORE}::beta",)
    assert len(sel.nodes) < len(tests)


@pytest.mark.sr("SR-255")
def test_no_function_changed_uses_the_closure(project: Path) -> None:
    """A path whose functions are all as recorded (a comment, a reformat, an explicit
    --paths) keeps today's covering tests: never nothing."""
    core = open_core(project)
    fm = _record(core, {n: ["alpha"] for n in EXEC_NODES})
    write(project, CORE, "# a comment" + chr(10) + CORE_TEXT.replace("x + 1", "(x + 1)"))
    sel = _select(project, fm, [CORE])
    assert sel.reasons["tests/test_imports_03.py"] == "import"
    assert sel.unrecorded == ()


@pytest.mark.sr("SR-255")
def test_tests_with_no_record_still_come_by_closure(project: Path) -> None:
    core = open_core(project)
    fm = _record(core, {n: ["alpha"] for n in EXEC_NODES} | {
        k: v for k, v in IMPORTERS.items() if not k.startswith("tests/test_imports_0")})
    write(project, CORE, CORE_TEXT.replace("x + 1", "1 + x"))
    sel = _select(project, fm, [CORE])
    unknown = {f"tests/test_imports_0{i}.py" for i in range(10)}
    assert set(sel.nodes) == set(EXEC_NODES) | unknown
    assert all(sel.reasons[n] == "import" for n in unknown)


@pytest.mark.sr("SR-255")
def test_module_level_change_uses_the_closure(project: Path) -> None:
    core = open_core(project)
    fm = _record(core, {n: ["alpha"] for n in EXEC_NODES})
    write(project, CORE, CORE_TEXT + "LIMIT = 3\n")
    sel = _select(project, fm, [CORE])
    assert sel.reasons["tests/test_imports_03.py"] == "import"
    assert sel.unrecorded == ()


@pytest.mark.sr("SR-255")
def test_cli_lines(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from plumb.verify.cli import cmd_select

    core = open_core(project)
    core.add_link("SR-001", "implemented_by", Target(path=CORE))
    _record(core, {EXEC_NODES[0]: ["alpha"]}, env=open_verify(core).env_key()).close()
    write(project, CORE, CORE_TEXT + "\n\ndef gamma(x):\n    return x\n")
    assert cmd_select("plumb tests select", [CORE, "--root", str(project), "--budget", "1000"]) == 0
    out = capsys.readouterr().out
    assert "no recorded test executes gamma" in out
    assert "tests/test_mod.py::test_add  (linked)" in out
    assert "(closure)" in out


@pytest.mark.sr("SR-255")
def test_coverage_off_is_todays_selection(project: Path) -> None:
    core = open_core(project)
    _record(core, {n: ["alpha"] for n in EXEC_NODES}, env=open_verify(core).env_key()).close()
    write(project, CORE, CORE_TEXT.replace("x + 1", "1 + x"))
    on = open_verify(open_core(project)).select([CORE], budget_s=1000)
    assert set(EXEC_NODES) <= set(on.nodes)
    write(project, ".plumb/config.yaml", "verify:\n  flaky_rerun: false\n  coverage: off\n")
    off = open_verify(open_core(project)).select([CORE], budget_s=1000)
    reference = select_tests(open_core(project), build_map(open_core(project)), [CORE],
                             budget_s=1000)
    assert off.nodes == reference.nodes
    assert all(off.reasons[n] != "executed" for n in off.nodes)
