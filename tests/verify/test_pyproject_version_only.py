"""SR-255 EX-9 with SR-254 EX-24 (owner, DEC-551): a pyproject.toml change sets full
verification pending, except one that changes only its [project] version, the landing's bump
(SR-377), which changes no test."""
from __future__ import annotations

from pathlib import Path

import pytest

from iaso.api import open_core
from iaso.verify import open_verify

pytestmark = pytest.mark.sr("SR-255")

PYPROJECT = ('[project]\nname = "x"\nversion = "{}"\n\n'
             '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')


def test_only_a_change_beyond_the_version_sets_full_pending(repo: Path) -> None:
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(PYPROJECT.format("0.1.0"), encoding="utf-8")
    open_verify(open_core(repo)).run(full=True)
    assert not open_verify(open_core(repo)).full_pending().pending
    (repo / "pyproject.toml").write_text(PYPROJECT.format("0.2.0"), encoding="utf-8")
    assert not open_verify(open_core(repo)).full_pending().pending
    (repo / "pyproject.toml").write_text(PYPROJECT.format("0.2.0") + 'markers = ["slow"]\n',
                                         encoding="utf-8")
    pending = open_verify(open_core(repo)).full_pending()
    assert pending.pending and "pyproject.toml changed" in pending.reasons
