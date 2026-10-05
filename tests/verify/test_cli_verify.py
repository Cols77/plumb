"""V6: ``plumb tests map|select|run`` and the aliases ``map`` and ``verify`` (spec 7, 9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from plumb import cli


@pytest.fixture
def project(repo: Path) -> Path:
    make_project(repo)
    commit_all(repo)
    return repo


def _json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


@pytest.mark.sr("SR-016")
@pytest.mark.sr("SR-017")
def test_tests_map_select_run_commands(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--root", str(project)]
    assert cli.main(["tests", "map", *root]) == 0
    out = capsys.readouterr().out
    assert ".plumb/test_map.txt" in out
    assert (project / ".plumb" / "test_map.txt").exists()
    assert cli.main(["tests", "map", "--json", *root]) == 0
    data = _json(capsys)
    assert data["sources"]["src/pkg/helper.py"] == ["tests/test_helper.py"]

    assert cli.main(["tests", "select", "src/pkg/helper.py", "--json", *root]) == 0
    sel = _json(capsys)
    assert sel["nodes"] == ["tests/test_helper.py"]
    assert sel["reasons"]["tests/test_helper.py"] == "import"
    assert cli.main(["tests", "select", "docs/guide.md", *root]) == 0
    assert "documentation only" in capsys.readouterr().out

    write(project, "src/pkg/helper.py", "from pkg.mod import add\n\n\ndef twice(a):\n"
          "    return add(a, a)  # edited\n")
    assert cli.main(["tests", "run", "--changed", *root]) == 0
    out = capsys.readouterr().out
    assert "plumb: ran 1 test" in out and "1 passed" in out
    assert cli.main(["tests", "run", "--paths", "src/pkg/mod.py", "--json", *root]) == 0
    run = _json(capsys)
    assert set(run["outcomes"]) == {"tests/test_mod.py::test_add",
                                    "tests/test_mod.py::test_add_zero",
                                    "tests/test_helper.py::test_twice"}


@pytest.mark.sr("SR-020")
def test_run_prints_regression_instruction(project: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--root", str(project)]
    assert cli.main(["tests", "run", "--nodes", "tests/test_mod.py::test_add", *root]) == 0
    capsys.readouterr()
    write(project, "src/pkg/mod.py", "def add(a, b):\n    return a - b\n")
    assert cli.main(["tests", "run", "--nodes", "tests/test_mod.py::test_add", *root]) == 1
    out = capsys.readouterr().out
    assert "plumb: regression: tests/test_mod.py::test_add passed in run " in out
    assert "and now fails. Tell the owner, with a read-back, and ask how to proceed." in out
    write(project, "tests/test_new.py", "def test_red():\n    assert False\n")
    assert cli.main(["tests", "run", "--nodes", "tests/test_new.py", *root]) == 1
    out = capsys.readouterr().out
    assert "not yet passing: tests/test_new.py::test_red" in out
    assert "regression" not in out


@pytest.mark.sr("SR-016")
@pytest.mark.sr("SR-018")
def test_aliases_map_and_verify(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--root", str(project)]
    assert cli.main(["map", "--json", *root]) == 0
    assert "sources" in _json(capsys)
    assert cli.main(["verify", "--nodes", "tests/test_helper.py", "--json", *root]) == 0
    assert _json(capsys)["outcomes"] == {"tests/test_helper.py::test_twice": "passed"}
    assert cli.main(["tests", "--help"]) == 0
    capsys.readouterr()
    assert cli.main(["tests", "bogus", *root]) == 2
