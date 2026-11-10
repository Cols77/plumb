"""SR-132 EX-2: a repository whose default branch is master and whose config does not name the
base is compared with master, not with a main that is not there."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git

from iaso.api import open_core
from iaso.awareness import publish
from iaso.boundary.cli import merge_settings

pytestmark = pytest.mark.sr("SR-216")


def test_the_base_is_detected_when_the_config_does_not_set_it(repo: Path) -> None:
    assert merge_settings(open_core(repo))["default_base"] == "main"
    git(repo, "branch", "-m", "main", "master")
    core = open_core(repo)
    assert merge_settings(core)["default_base"] == "master"
    assert publish.default_branch(core) == "master"


def test_a_configured_base_wins(repo: Path) -> None:
    git(repo, "branch", "-m", "main", "master")
    config = repo / ".iaso" / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "\nmerge:\n  default_base: trunk\n",
                      encoding="utf-8")
    assert merge_settings(open_core(repo))["default_base"] == "trunk"
