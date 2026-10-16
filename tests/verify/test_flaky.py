"""VS1 and VS2: removed-after-passing nodes and the same-tree flaky rerun (spec 7.5)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from verify_helpers import commit_all, make_project, write

from plumb.api import open_core
from plumb.verify import open_verify


@pytest.fixture
def project(repo: Path) -> Path:
    make_project(repo)
    write(repo, ".plumb/config.yaml", "verify:\n  flaky_rerun: true\n")
    write(repo, ".gitignore", "__pycache__/\n")
    commit_all(repo)
    return repo


@pytest.mark.sr("SR-254")
def test_flaky_rerun_same_tree_records_both_attempts(project: Path, tmp_path: Path) -> None:
    flag = (tmp_path / f"flag-{uuid.uuid4().hex}").as_posix()
    write(project, "tests/test_flaky.py",
          "from pathlib import Path\n\n\ndef test_once():\n"
          f"    flag = Path({flag!r})\n    if not flag.exists():\n"
          "        flag.write_text('x')\n        assert False\n")
    commit_all(project)
    report = open_verify(open_core(project)).run(nodes=["tests/test_flaky.py"])
    node = "tests/test_flaky.py::test_once"
    assert report.outcomes[node] == "flaky"
    assert report.flaky == [node]
    assert report.ok
    payload = open_core(project).log_read("evidence", ["test-run"])
    last = list(payload)[-1].payload
    assert last["nodes"][0]["attempts"] == ["failed", "passed"]
    ev = open_verify(open_core(project)).evidence([node])[node]
    assert ev.state == "flaky-pass"


@pytest.mark.sr("SR-254")
def test_no_rerun_when_tree_changed(project: Path) -> None:
    write(project, "tests/test_dirty.py",
          "from pathlib import Path\n\n\ndef test_dirties():\n"
          "    Path('README.md').write_text('changed\\n')\n    assert False\n")
    commit_all(project)
    report = open_verify(open_core(project)).run(nodes=["tests/test_dirty.py"])
    assert report.outcomes["tests/test_dirty.py::test_dirties"] == "failed"
    last = list(open_core(project).log_read("evidence", ["test-run"]))[-1].payload
    assert last["nodes"][0]["attempts"] == ["failed"]


@pytest.mark.sr("SR-254")
def test_removed_after_passing_listed(project: Path) -> None:
    first = open_verify(open_core(project)).run(nodes=["tests/test_mod.py"])
    assert first.ok
    write(project, "tests/test_mod.py",
          "from pkg.mod import add\n\n\ndef test_add_renamed():\n    assert add(1, 2) == 3\n")
    verify = open_verify(open_core(project))
    assert verify.removed_after_passing() == ["tests/test_mod.py::test_add",
                                              "tests/test_mod.py::test_add_zero"]
    report = verify.run(nodes=["tests/test_mod.py"])
    assert report.removed_after_passing == ["tests/test_mod.py::test_add",
                                            "tests/test_mod.py::test_add_zero"]
    (project / "tests" / "test_mod.py").unlink()
    assert open_verify(open_core(project)).removed_after_passing() == []
