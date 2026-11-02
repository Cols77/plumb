"""SR-380 EX-1 and EX-5: the removed surfaces do not exist."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from plumb import cli

pytestmark = pytest.mark.sr("SR-380")


@pytest.mark.parametrize("words", [["view"], ["import"], ["mcp"], ["triage"]])
def test_ex1_a_removed_command_does_not_exist(words, repo: Path, capsys) -> None:
    cli.main([*words, "--root", str(repo)])
    out = capsys.readouterr()
    assert "unknown command" in out.err + out.out


def test_ex1_spec_approve_does_not_exist(repo: Path, capsys) -> None:
    assert cli.main(["spec", "approve", "INT-001", "--root", str(repo)]) != 0
    assert "invalid choice" in capsys.readouterr().err


def test_ex5_no_card_press_surface_is_left(capsys) -> None:
    assert importlib.util.find_spec("plumb.mod.press") is None
    assert importlib.util.find_spec("plumb.mod.offers") is None
    assert cli.main(["mod", "press", "--session", "s1"]) != 0
    assert "invalid choice" in capsys.readouterr().err
