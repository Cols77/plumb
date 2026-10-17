"""The line `plumb repin --after-tests` prints for each diagnosis, one per outcome."""

from __future__ import annotations

import pytest

from plumb.commands import _diagnosis_line
from plumb.understand.repin import OUTCOMES


def _item(outcome: str) -> dict[str, object]:
    return {"link": "SR-279#2", "record": "SR-279", "outcome": outcome, "topic": "Plugin copy",
            "explanation": "the hook now runs the checkout's code", "proposed_wording": "w",
            "card": False, "other": "SR-315"}


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_every_outcome_has_a_line(outcome: str) -> None:
    assert _diagnosis_line(_item(outcome), dry_run=False).startswith("plumb: SR-279#2")


@pytest.mark.sr("SR-198")
def test_contradicts_names_the_other_record() -> None:
    line = _diagnosis_line(_item("contradicts"), dry_run=False)
    assert "SR-315" in line and "the hook now runs the checkout's code" in line
