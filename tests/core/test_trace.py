"""Untraced changes: changed source paths no requirement link owns (spec 5.11, 6.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.contracts import Target
from plumb.trace import owned_paths, untraced_paths

pytestmark = pytest.mark.sr("SR-026")

SR1 = """---
id: SR-001
title: Adds numbers
statement: add returns the sum.
---
"""


@pytest.fixture
def linked(repo: Path, write_record) -> Path:
    write_record(repo, SR1)
    for rel in ("src/calc.py", "tests/test_calc.py", "src/mul.py"):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_calc.py"))
    return repo


def test_owned_paths_are_requirement_code_and_test_ends(linked: Path) -> None:
    assert owned_paths(open_core(linked)) == {"src/calc.py", "tests/test_calc.py"}


def test_unlinked_source_path_is_untraced(linked: Path) -> None:
    core = open_core(linked)
    assert untraced_paths(core, ["src/calc.py", "src/mul.py"]) == ["src/mul.py"]


def test_docs_records_tests_and_infra_are_never_untraced(linked: Path) -> None:
    core = open_core(linked)
    paths = ["README.md", "docs/guide.md", ".plumb/requirements/SR-001.md",
             "tests/test_other.py", "tests/conftest.py", "pyproject.toml", "uv.lock",
             "scripts/tool.py", ".claude/settings.json",
             "src/__pycache__/mul.cpython-312.pyc", "src/pkg.egg-info/PKG-INFO"]
    assert untraced_paths(core, paths) == []


def test_owner_exempt_globs_are_not_untraced(linked: Path) -> None:
    (linked / ".plumb" / "config.yaml").write_text(
        "trace:\n  exempt: [\"src/gen/*\"]\n", encoding="utf-8")
    core = open_core(linked)
    assert untraced_paths(core, ["src/gen/table.py", "src/mul.py"]) == ["src/mul.py"]


def test_windows_separators_and_duplicates_are_normalized(linked: Path) -> None:
    core = open_core(linked)
    assert untraced_paths(core, ["src\\mul.py", "src/mul.py", "src\\calc.py"]) == [
        "src/mul.py"]
