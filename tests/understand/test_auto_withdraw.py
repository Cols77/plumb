"""SR-161: a card whose question no longer stands is withdrawn by plumb, at the turn end and
right after the link it holds is settled, and the turn end says so once."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.test_stale_resolve import (  # noqa: F401
    LINK,
    REFORMATTED,
    Runner,
    _backend,
    _edit,
    project,
)

from plumb import links, stale
from plumb.api import open_core
from plumb.understand import cardstore
from understand.test_judge_job import SESSION

pytestmark = pytest.mark.sr("SR-216")


def _card_for_link(root: Path) -> None:
    stale.add_card(root, SESSION, link=LINK, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="the code changed", options=["keep", "undo"])


def test_ex1_repin_withdraws_the_stale_card(project: Path) -> None:
    _edit(project, REFORMATTED)
    _card_for_link(project)
    links.repin_after_tests(open_core(project), LINK, runner=Runner(), judge=_backend("cosmetic"))
    assert cardstore.stale_cards(project, SESSION) == []
    (event,) = open_core(project).log_read("events", ["card-withdrawn"])
    assert event.payload["card"] == f"stale:{LINK}"


def test_unlink_withdraws_the_card_of_a_link_that_is_gone(project: Path) -> None:
    _edit(project, REFORMATTED)
    _card_for_link(project)
    links.unlink(open_core(project), LINK, "the code moved")
    assert cardstore.stale_cards(project, SESSION) == []
