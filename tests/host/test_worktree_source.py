"""SR-303: a worktree's tests and plugin build use the worktree's own files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.sr("SR-303")


def test_ex1_the_tests_import_the_source_of_the_checkout_they_run_in() -> None:
    import iaso

    assert Path(iaso.__file__).resolve().is_relative_to(REPO / "src")


def test_ex2_the_plugin_build_writes_only_under_the_repo_it_runs_from() -> None:
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import build_plugin
    finally:
        sys.path.remove(str(REPO / "scripts"))
    assert build_plugin.REPO == REPO
    assert all(p.is_relative_to(REPO) for p in build_plugin.text_files())
    assert build_plugin.VENDOR.is_relative_to(REPO)
