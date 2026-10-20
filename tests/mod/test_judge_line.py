"""SR-251 EX-1: a judge approval gets no line of the band; the band's status counts it (the
mod reads ``confirmed_by`` from status.json). ``present.json`` keeps the owner's own
confirmations and drops the judge-approval line."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from plumb.mod import handshake
from plumb.present.owner_text import JUDGE_APPROVED

pytestmark = pytest.mark.sr("SR-251")


def test_sr251_ex1_no_band_line_for_a_judge_approval_alone(repo: Path) -> None:
    said = "Late fees: you said 'yes, that is right'"
    parts = types.SimpleNamespace(confirmations=(said, f"1 {JUDGE_APPROVED}"), cards=())
    ctx = types.SimpleNamespace(root=repo, session_id="s1", extra={"stop_parts": parts})
    data = handshake.write_present(ctx, {"turn_start": 1000.0})
    assert data["confirmations"] == [said]
