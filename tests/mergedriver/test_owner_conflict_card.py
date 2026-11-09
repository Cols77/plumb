"""SR-151: merge and early conflict cards reach the owner to the agent with their id."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mergedriver.mdhelpers import conflicted
from iaso import cli

pytestmark = pytest.mark.sr("SR-267")
IDS = re.compile(r"\b(IC|SR|INT|DEC)-\d+")


def test_ex2_agent_view_keeps_the_conflict_id(repo: Path, capsys) -> None:
    ic = conflicted(repo)
    assert cli.main(["conflicts", "--root", str(repo)]) == 0
    assert ic in capsys.readouterr().out
