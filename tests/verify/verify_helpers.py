"""Small temporary pytest projects for the VERIFY lane's tests (not a conftest)."""

from __future__ import annotations

import subprocess
from pathlib import Path

SR_TEXT = """---
id: SR-001
title: Modules add numbers
feature: FEAT-001
statement: The module adds numbers.
examples:
  - {id: EX-1, given: two numbers, when: added, then: the sum is returned}
---
"""

PYPROJECT = """[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["sr(id): links a test to a plumb requirement"]
"""


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def make_project(root: Path) -> Path:
    """A tiny src-layout package with three test modules."""
    write(root, "pyproject.toml", PYPROJECT)
    write(root, "src/pkg/__init__.py", "")
    write(root, "src/pkg/mod.py", "def add(a, b):\n    return a + b\n")
    write(root, "src/pkg/helper.py", "from pkg.mod import add\n\n\ndef twice(a):\n"
          "    return add(a, a)\n")
    write(root, "src/pkg/lonely.py", "VALUE = 1\n")
    write(root, "tests/test_mod.py",
          "import pytest\n\nfrom pkg.mod import add\n\n\n@pytest.mark.sr(\"SR-001\")\n"
          "def test_add():\n    assert add(1, 2) == 3\n\n\ndef test_add_zero():\n"
          "    assert add(0, 0) == 0\n")
    write(root, "tests/test_helper.py",
          "from pkg.helper import twice\n\n\ndef test_twice():\n    assert twice(2) == 4\n")
    write(root, "tests/test_paths.py",
          "def test_mentions():\n    assert 'src/pkg/lonely.py'.endswith('.py')\n")
    write(root, "docs/guide.md", "# guide\n")
    return root


def commit_all(root: Path, message: str = "work") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True,
                   capture_output=True)
