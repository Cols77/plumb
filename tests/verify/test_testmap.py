"""V2: the grep-able test map from links, markers, imports and naming (spec 7.1)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, make_project, write

from iaso.api import open_core
from iaso.contracts import Target
from iaso.verify.testmap import build_map


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo)
    write_record(repo, SR_TEXT)
    return repo


@pytest.mark.sr("SR-255")
def test_map_from_verified_by_links(project: Path) -> None:
    core = open_core(project)
    core.add_link("SR-001", "verified_by", Target(test="tests/test_helper.py::test_twice"))
    core = open_core(project)
    tmap = build_map(core)
    assert "tests/test_helper.py::test_twice" in tmap.records["SR-001"]


@pytest.mark.sr("SR-255")
def test_map_from_sr_markers(project: Path) -> None:
    tmap = build_map(open_core(project))
    assert tmap.records["SR-001"] == ["tests/test_mod.py::test_add"]


@pytest.mark.sr("SR-255")
def test_map_from_import_closure(project: Path) -> None:
    tmap = build_map(open_core(project))
    assert tmap.covering("src/pkg/mod.py") == ["tests/test_mod.py", "tests/test_helper.py"]
    assert tmap.covering("src/pkg/helper.py") == ["tests/test_helper.py"]
    assert tmap.closures["tests/test_helper.py"]["src/pkg/mod.py"] == 2


@pytest.mark.sr("SR-255")
def test_map_text_is_grepable(project: Path) -> None:
    build_map(open_core(project))
    lines = (project / ".iaso" / "test_map.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# iaso test map v1")
    assert "src/pkg/mod.py -> tests/test_mod.py tests/test_helper.py" in lines
    assert "SR-001 -> tests/test_mod.py::test_add" in lines
    helper = next(line for line in lines if line.startswith("tests/test_helper.py <- "))
    deps = helper.split(" <- ", 1)[1].split()
    assert deps.index("src/pkg/helper.py") < deps.index("src/pkg/mod.py")


@pytest.mark.sr("SR-255")
def test_map_cache_reparses_only_changed_files(project: Path) -> None:
    first = build_map(open_core(project))
    assert first.parsed >= 7
    second = build_map(open_core(project))
    assert second.parsed == 0
    path = project / "src" / "pkg" / "lonely.py"
    path.write_text("VALUE = 2\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000))
    third = build_map(open_core(project))
    assert third.parsed == 1
    assert third.files["src/pkg/lonely.py"]["hash"] != first.files["src/pkg/lonely.py"]["hash"]


@pytest.mark.sr("SR-255")
def test_map_from_naming(project: Path) -> None:
    write(project, "src/pkg/widget.py", "X = 1\n")
    write(project, "tests/test_widget.py", "def test_widget():\n    assert True\n")
    tmap = build_map(open_core(project))
    assert tmap.covering("src/pkg/widget.py") == ["tests/test_widget.py"]
    assert tmap.reason("src/pkg/widget.py", "tests/test_widget.py") == "naming"
