"""A copy of the pi-agent-factory register fixtures for the importer tests.

Not a ``conftest.py``: the suite imports the top-level ``tests/conftest.py`` as the module
``conftest`` (``from conftest import git``), which a second conftest would shadow.
"""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "pi_factory"


def make_pi_source(tmp_path: Path) -> Path:
    """A pi-agent-factory-shaped source tree (copies of real records, read once)."""
    source = tmp_path / "pi-src"
    shutil.copytree(FIXTURES, source)
    git = source / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("0123456789abcdef0123456789abcdef01234567\n",
                                                encoding="utf-8")
    return source
