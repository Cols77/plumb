"""SR-255 EX-9 has no exception: a version-only pyproject.toml change is a change to it, so
full verification goes pending. A landing is freed by the run of its tree in another checkout
(tests/merge/test_fullrun_other_checkout.py), not by ignoring the line."""
from __future__ import annotations

from pathlib import Path

import pytest

from plumb.api import open_core
from plumb.verify import open_verify

pytestmark = pytest.mark.sr("SR-255")

PYPROJECT = ('[project]\nname = "x"\nversion = "{}"\n\n'
             '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')


def test_version_only_change_sets_full_pending(repo: Path) -> None:
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT.format("0.1.0"), encoding="utf-8")
    open_verify(open_core(repo)).run(full=True)
    assert not open_verify(open_core(repo)).full_pending().pending
    (repo / "pyproject.toml").write_text(PYPROJECT.format("0.2.0"), encoding="utf-8")
    pending = open_verify(open_core(repo)).full_pending()
    assert pending.pending and "pyproject.toml changed" in pending.reasons
