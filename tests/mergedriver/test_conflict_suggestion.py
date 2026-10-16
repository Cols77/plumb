"""SR-158: the agent can suggest how to resolve a conflict; the suggestion chooses nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergedriver.mdhelpers import conflicted
from plumb import cli
from plumb.api import open_core
from plumb.mergedriver import open_conflicts
from plumb.mergedriver.conflicts import propose
from plumb.understand import cards, fullcard

pytestmark = pytest.mark.sr("SR-211")


def _options(core, conflict) -> list[dict]:
    return fullcard.content(core, cards.conflict_card(core.index(), conflict))["options"]


def test_ex1_a_suggested_side_comes_first_recommended_with_its_reason(repo: Path) -> None:
    conflicted(repo)
    core = open_core(repo)
    (conflict,) = open_conflicts(core)
    theirs = conflict.labels[1]
    conflict = propose(core, conflict.ic, None, take="theirs", why="it only fixes the wording")
    options = _options(core, conflict)
    assert options[0]["text"] == cards.KEEP_OTHER and options[0]["recommended"]
    assert not any(o["recommended"] for o in options[1:])
    text = fullcard.render(fullcard.content(core, cards.conflict_card(core.index(), conflict)))
    assert f"Suggested: keep {theirs}'s version. it only fixes the wording" in text
    assert open_conflicts(open_core(repo))     # still open: the suggestion chose nothing


def test_ex2_a_suggested_combined_version_comes_first(repo: Path) -> None:
    conflicted(repo)
    core = open_core(repo)
    (conflict,) = open_conflicts(core)
    conflict = propose(core, conflict.ic, {"statement": "both hold together"},
                       take="combined", why="both rules can hold at once")
    options = _options(core, conflict)
    assert options[0]["recommended"] and "combined" in options[0]["consequence"]


def test_ex3_no_suggestion_no_recommendation(repo: Path) -> None:
    conflicted(repo)
    core = open_core(repo)
    (conflict,) = open_conflicts(core)
    assert not any(o["recommended"] for o in _options(core, conflict))


def test_a_suggestion_needs_its_reason(repo: Path, capsys) -> None:
    ic = conflicted(repo)
    assert cli.main(["conflict", "propose", ic, "--take", "theirs", "--root", str(repo)]) == 2
    assert "--why" in capsys.readouterr().err
    assert cli.main(["conflict", "propose", ic, "--take", "theirs", "--why", "typo fix",
                     "--root", str(repo)]) == 0
