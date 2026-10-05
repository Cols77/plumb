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
             ".claude/settings.json", ".github/workflows/ci.sh", "LICENSE", "data.json",
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


@pytest.mark.sr("SR-029")
def test_flat_layout_and_root_code_files_are_source_by_default(linked: Path) -> None:
    """No source_dirs in config.yaml: a code file outside tests, docs and dot dirs is source,
    so a repository not laid out as src/ is not invisible to the trace."""
    core = open_core(linked)
    assert not core.config.source_dirs_set
    paths = ["mypkg/extra.py", "tool.py", "app/main.py", "scripts/tool.py", "web/app.ts",
             "docs/conf.py", "mypkg/__pycache__/x.cpython-312.pyc", "venv/lib/x.py"]
    assert untraced_paths(core, paths) == ["mypkg/extra.py", "tool.py", "app/main.py",
                                           "scripts/tool.py", "web/app.ts"]


@pytest.mark.sr("SR-029")
def test_configured_source_dirs_are_the_only_source(linked: Path) -> None:
    (linked / ".plumb" / "config.yaml").write_text("source_dirs: [lib]\n", encoding="utf-8")
    core = open_core(linked)
    assert core.config.source_dirs_set
    assert untraced_paths(core, ["lib/x.py", "tool.py", "src/mul.py"]) == ["lib/x.py"]


@pytest.mark.sr("SR-029")
def test_verify_selection_shares_the_source_definition(linked: Path) -> None:
    """The covering-test selection samples for the same paths the trace calls source."""
    from plumb.trace import is_code_path

    core = open_core(linked)
    for rel, expected in (("mypkg/extra.py", True), ("tool.py", True), ("README.md", False),
                          ("tests/test_x.py", False), (".plumb/config.yaml", False)):
        assert is_code_path(core.config, rel) is expected, rel
