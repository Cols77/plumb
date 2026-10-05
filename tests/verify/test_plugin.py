"""V4: the pytest plugin's report, read through the runner (spec 7.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from verify_helpers import write

from plumb.verify.runner import run_pytest


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    write(root, "pytest.ini", "[pytest]\n")
    write(root, "tests/test_a.py",
          "import pytest\n\n\ndef test_ok():\n    pass\n\n\ndef test_bad():\n    assert 0\n\n\n"
          "@pytest.fixture\ndef broken_teardown():\n    yield\n    raise RuntimeError('td')\n\n\n"
          "def test_teardown(broken_teardown):\n    pass\n")
    return root


@pytest.mark.sr("SR-018")
def test_plugin_reports_phases_and_exit_status(proj: Path) -> None:
    result = run_pytest(proj, ["tests/test_a.py::test_ok", "tests/test_a.py::test_bad"])
    assert result.finished is True
    assert result.exit_status == 1
    assert result.nodes["tests/test_a.py::test_ok"]["outcome"] == "passed"
    assert result.nodes["tests/test_a.py::test_bad"]["outcome"] == "failed"
    assert result.nodes["tests/test_a.py::test_ok"]["duration_s"] >= 0


@pytest.mark.sr("SR-018")
def test_setup_failure_outranks_pass(proj: Path) -> None:
    result = run_pytest(proj, ["tests/test_a.py::test_teardown"])
    assert result.nodes["tests/test_a.py::test_teardown"]["outcome"] == "failed"
    assert result.nodes["tests/test_a.py::test_teardown"]["failed_phase"] == "teardown"


@pytest.mark.sr("SR-018")
def test_collection_error_reported(proj: Path) -> None:
    write(proj, "tests/test_broken.py", "def test_x(:\n    pass\n")
    result = run_pytest(proj, ["tests/test_broken.py"])
    assert result.collection_errors == ["tests/test_broken.py"]
    # pytest's own status: 1 under --continue-on-collection-errors (2 without it)
    assert result.exit_status == 1
