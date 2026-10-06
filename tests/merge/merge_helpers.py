"""Small repositories for the MERGE lane's tests (not a conftest)."""

from __future__ import annotations

import subprocess
from pathlib import Path

INT = "---\nid: INT-001\ntitle: Grounded\nquote: q\nreadback: Ground the work.\n---\n"
SR1 = """---
id: SR-001
title: add returns the sum
statement: add(a, b) returns a + b.
examples:
  - {id: EX-1, given: 1 and 2, when: add runs, then: it returns 3}
---
"""
SR2 = "---\nid: SR-002\ntitle: Other\nstatement: Something else.\n---\n"
PYPROJECT = """[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["sr(id): links a test to a plumb requirement"]
"""
MOD = "def add(a, b):\n    return a + b\n"
TEST = ("import pytest\n\nfrom pkg.mod import add\n\n\n@pytest.mark.sr(\"SR-001\")\n"
        "def test_add():\n    assert add(1, 2) == 3\n")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def records(root: Path) -> None:
    """INT-001, SR-001 (implemented by src/pkg/mod.py, verified by tests/test_mod.py EX-1)
    and SR-002, with every link pinned."""
    from plumb.api import open_core
    from plumb.contracts import Target

    write(root, ".plumb/intents/INT-001.md", INT)
    write(root, ".plumb/requirements/SR-001.md", SR1)
    write(root, ".plumb/requirements/SR-002.md", SR2)
    core = open_core(root)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/pkg/mod.py"))
    core.add_link("SR-001", "verified_by", Target(path="tests/test_mod.py"), example="EX-1")
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))


def project(root: Path, *, test: str = TEST) -> Path:
    """A tiny src-layout package with one acceptance test, and the records above."""
    write(root, "pyproject.toml", PYPROJECT)
    write(root, ".gitignore", "__pycache__/\n.pytest_cache/\n")
    write(root, "src/pkg/__init__.py", "")
    write(root, "src/pkg/mod.py", MOD)
    write(root, "tests/test_mod.py", test)
    write(root, ".plumb/config.yaml", "verify:\n  flaky_rerun: false\n")
    records(root)
    return root


def repin_all(root: Path) -> None:
    from plumb.api import open_core
    from plumb.links import repin

    repin(open_core(root), all_stale=True)
