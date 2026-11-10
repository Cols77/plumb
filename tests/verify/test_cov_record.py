"""HB3: recording which functions each test executes (SR-110), with coverage contexts."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import SR_TEXT, make_project, write

from iaso.api import open_core
from iaso.verify import open_verify
from iaso.verify.funcmap import FuncMap

MOD = "src/pkg/mod.py"
NODES = {"tests/test_mod.py::test_add", "tests/test_mod.py::test_add_zero",
         "tests/test_helper.py::test_twice", "tests/test_paths.py::test_mentions"}


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    make_project(repo)
    write_record(repo, SR_TEXT)
    return repo


def _verify(root: Path):
    return open_verify(open_core(root), hook=False)


def _map(root: Path, **kw):
    verify = _verify(root)
    report = verify.map_coverage(**kw)
    return verify, report


@pytest.mark.sr("SR-255")
def test_collect_once_records_every_test(project: Path) -> None:
    verify, report = _map(project)
    assert set(report.recorded) == NODES
    assert report.absent is False
    fm = FuncMap.open(verify.core)
    assert fm.tests_executing(MOD, "add") == ["tests/test_helper.py::test_twice",
                                              "tests/test_mod.py::test_add",
                                              "tests/test_mod.py::test_add_zero"]
    assert fm.tests_executing("src/pkg/helper.py", "twice") == [
        "tests/test_helper.py::test_twice"]
    assert fm.tests_executing(MOD, "add", "other-env") == []


@pytest.mark.sr("SR-255")
def test_unchanged_test_not_rerun_for_recording(project: Path) -> None:
    _map(project)
    _, again = _map(project)
    assert again.ran == []
    assert again.recorded == []
    assert again.fresh == len(NODES)


@pytest.mark.sr("SR-255")
def test_refresh_only_stale_tests(project: Path) -> None:
    _map(project)
    write(project, "tests/test_helper.py",
          "from pkg.helper import twice\n\n\ndef test_twice():\n    assert twice(3) == 6\n")
    _, report = _map(project)
    assert report.ran == ["tests/test_helper.py::test_twice"]
    assert report.recorded == ["tests/test_helper.py::test_twice"]


@pytest.mark.sr("SR-255")
def test_workers_combine_data_files(project: Path, tmp_path: Path) -> None:
    from coverage import CoverageData

    from iaso.verify.funcmap import combine_data_files

    parts = []
    for i, ctx in enumerate(["a::t1", "b::t2"]):
        name = str(tmp_path / f"part.{i}")
        data = CoverageData(basename=name)
        data.set_context(ctx)
        data.add_lines({str(project / MOD): [2]})
        data.write()
        parts.append(name)
    combined = combine_data_files(parts, str(tmp_path / "combined"))
    assert set(combined.measured_contexts()) == {"a::t1", "b::t2"}
    write(project, ".iaso/config.yaml", "verify:\n  flaky_rerun: false\n  workers: 2\n")
    verify, report = _map(project)
    assert report.workers == 2
    assert set(report.recorded) == NODES


@pytest.mark.sr("SR-255")
def test_coverage_absent_says_so_and_selects_by_closure(project: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from iaso.verify import runner

    monkeypatch.setattr(runner, "coverage_available", lambda: False)
    verify, report = _map(project)
    assert report.absent is True
    assert report.recorded == []
    assert any("coverage is not installed" in note for note in report.notes)
    assert not FuncMap.open(verify.core).exists()
    sel = verify.select([MOD])
    assert sel.reasons["tests/test_helper.py"] == "import"
