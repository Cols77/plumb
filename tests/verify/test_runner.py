"""V4: the runner: command line, hard limit, inputs-changed discard (spec 7.3, 7.4)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from iaso.api import open_core
from iaso.verify import open_verify
from iaso.verify.runner import build_command, run_pytest, run_selection


@pytest.mark.sr("SR-255")
def test_run_never_passes_n_by_default() -> None:
    cmd = build_command(["tests/test_a.py"], workers=0)
    assert cmd[:3] == [sys.executable, "-m", "pytest"]
    assert "-p" in cmd and "iaso.verify.pytest_plugin" in cmd
    assert "-n" not in cmd
    assert "-n" not in build_command(["tests/test_a.py"], workers=5, xdist=True)
    assert "-n" not in build_command(["tests/test_a.py"], workers=2, xdist=False)
    with_n = build_command(["tests/test_a.py"], workers=2, xdist=True)
    assert with_n[with_n.index("-n") + 1] == "2"


@pytest.mark.sr("SR-255")
def test_hard_limit_terminates_own_child(tmp_path: Path) -> None:
    root = tmp_path / "slow"
    write(root, "pytest.ini", "[pytest]\n")
    write(root, "tests/test_slow.py", "import time\n\n\ndef test_slow():\n    time.sleep(60)\n")
    start = time.monotonic()
    result = run_pytest(root, ["tests/test_slow.py"], timeout_s=4)
    assert result.timed_out is True
    assert time.monotonic() - start < 20
    assert result.finished is False


@pytest.mark.sr("SR-255")
def test_timeout_keeps_the_tests_that_finished_before_it(tmp_path: Path) -> None:
    """A timed-out run still reports every test that completed (setup, call, teardown)."""
    root = tmp_path / "partial"
    write(root, "pytest.ini", "[pytest]\n")
    write(root, "tests/test_mix.py",
          "import time\n\n\ndef test_a():\n    pass\n\n\ndef test_b():\n    assert 0\n\n\n"
          "def test_c():\n    time.sleep(60)\n")
    result = run_pytest(root, ["tests/test_mix.py"], timeout_s=12)
    assert result.timed_out is True and result.finished is False
    assert result.nodes["tests/test_mix.py::test_a"]["outcome"] == "passed"
    assert result.nodes["tests/test_mix.py::test_b"]["outcome"] == "failed"
    assert "tests/test_mix.py::test_c" not in result.nodes  # never finished
    assert result.exit_status is None


@pytest.mark.sr("SR-255")
def test_run_discarded_when_inputs_change(repo: Path) -> None:
    make_project(repo)
    write(repo, "tests/test_mutates.py",
          "from pathlib import Path\n\nimport pkg.mod\n\n\ndef test_mutate():\n"
          "    p = Path('src/pkg/mod.py')\n    p.write_text(p.read_text() + '# touched\\n')\n")
    outcome = run_selection(open_core(repo), ["tests/test_mutates.py"])
    assert outcome.discarded == "inputs changed"
    clean = run_selection(open_core(repo), ["tests/test_helper.py"])
    assert clean.discarded is None
    assert clean.result.nodes["tests/test_helper.py::test_twice"]["outcome"] == "passed"


@pytest.mark.sr("SR-255")
def test_collection_error_does_not_stop_other_files(repo: Path) -> None:
    assert "--continue-on-collection-errors" in build_command(["tests/test_a.py"])
    make_project(repo)
    write(repo, "tests/test_broken.py", "import nowhere_to_be_found\n\n\ndef test_x():\n"
          "    pass\n")
    result = run_pytest(repo, ["tests/test_broken.py", "tests/test_helper.py"], timeout_s=60)
    assert result.collection_errors == ["tests/test_broken.py"]
    assert result.nodes["tests/test_helper.py::test_twice"]["outcome"] == "passed"


def test_the_tests_run_in_the_repositorys_venv_when_it_has_one(tmp_path: Path) -> None:
    """Under the plugin, sys.executable is iaso's private environment, which has no pytest:
    a repository's .venv runs its tests; verify.python names another one; else iaso's."""
    from iaso.verify.runner import test_interpreter

    assert test_interpreter(tmp_path) == sys.executable
    venv = tmp_path / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    venv.parent.mkdir(parents=True)
    venv.write_bytes(b"")
    assert test_interpreter(tmp_path) == str(venv)
    assert test_interpreter(tmp_path, "C:/other/python.exe") == "C:/other/python.exe"
    assert build_command(["tests/test_a.py"], interpreter=str(venv))[0] == str(venv)


def test_an_interpreter_without_pytest_aborts_the_run_saying_so(repo: Path, monkeypatch) -> None:
    """No pytest in the interpreter is no test failure: nothing runs, no node is marked failed,
    and the report says what is missing (the plugin's own environment has no pytest)."""
    from iaso.verify import runner

    make_project(repo)
    commit_all(repo)
    missing = runner.PYTEST_MISSING.format(python="C:/no/pytest/python.exe")
    monkeypatch.setattr(runner, "_probe", lambda interpreter: (missing, False))
    report = open_verify(open_core(repo)).run(nodes=["tests/test_mod.py"])
    assert report.ok is False and report.aborted == missing
    assert report.failed == [] and report.outcomes == {}
