"""P2: the one-line status card with a plain-language intent summary (sp5 4.1, SR-061)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from present_helpers import INT1, SR1, SR2, run_stop, touch, write_all

from plumb.api import open_core
from plumb.contracts import StatusSnapshot
from plumb.hosts.claude_code import statusline
from plumb.hosts.claude_code.snapshot import build_snapshot, snapshot_dict
from plumb.present.render import card_state, status_card

pytestmark = pytest.mark.sr("SR-061")


def _snap(**kwargs) -> StatusSnapshot:
    base = dict(at="2026-10-06T00:00:00Z", requirements_total=14, requirements_confirmed=14,
                proposed=0, stale_links=0, dangling_links=0, tests="ok",
                intent_summary="add multiply next to add")
    base.update(kwargs)
    return StatusSnapshot(**base)


def test_awaits_you_with_jev_count() -> None:
    """EX-1: 12 of 14 confirmed, 2 by JEV, one proposed record."""
    card = status_card(_snap(requirements_confirmed=12, proposed=1,
                             confirmed_by={"owner": 10, "auto-jev": 2}))
    assert card == ('plumb ● awaits you · "add multiply next to add" · '
                    "SR 12/14 ok (2 by JEV) · 1 awaits you")


def test_aligned() -> None:
    assert status_card(_snap()).startswith('plumb ✓ aligned · "add multiply next to add"')


def test_drift() -> None:
    card = status_card(_snap(stale_links=2))
    assert card.startswith("plumb ▲ drift") and "2 stale" in card


def test_failing() -> None:
    card = status_card(_snap(tests="failing", failing=("t::a",), proposed=3))
    assert card.startswith("plumb ✗ failing")


def test_regression_wins_over_everything() -> None:
    card = status_card(_snap(tests="regression", regressions=("t::a",), failing=("t::a",),
                             proposed=3, stale_links=1))
    assert card.startswith("plumb ✗ regression")
    assert card_state(_snap(tests="regression")) == "regression"


def test_jev_count_only_with_auto_approvals() -> None:
    """EX-2: no auto-approval, no "by JEV" count."""
    card = status_card(_snap(confirmed_by={"owner": 14}))
    assert "JEV" not in card and "SR 14/14 ok" in card


def test_ascii_fallback() -> None:
    """EX-3: the ASCII card is ASCII only."""
    card = status_card(_snap(requirements_confirmed=12, proposed=1, full_pending=True,
                             auto_approve="suspended", intent_summary="ajouter la multiplication é",
                             confirmed_by={"auto-jev": 2}), ascii=True)
    assert card.isascii()
    assert card.startswith('plumb | awaits you | "ajouter la multiplication e"')
    assert "| full pending" in card and "| auto-approve suspended" in card


def test_intent_summary_is_clipped_to_forty_characters() -> None:
    card = status_card(_snap(intent_summary="x" * 60))
    summary = card.split('"')[1]
    assert len(summary) <= 40


def test_status_line_renders_the_card_without_recomputing(tmp_path: Path) -> None:
    snapshot = snapshot_dict(_snap(proposed=1, requirements_confirmed=12,
                                   confirmed_by={"auto-jev": 2}))
    assert statusline.render(snapshot) == status_card(snapshot)
    snapshot["present"] = {"ascii": True}
    assert statusline.render(snapshot).isascii()
    assert statusline.render({"bogus": 1}) == statusline.NO_STATUS
    old = {"requirements_total": 1, "requirements_confirmed": 1, "tests": "ok"}
    assert statusline.render(old).startswith("plumb ✓ aligned")


def test_status_line_falls_back_to_ascii_on_a_narrow_terminal(repo: Path) -> None:
    session = repo / ".plumb" / "session"
    session.mkdir(parents=True, exist_ok=True)
    (session / "status.json").write_text(json.dumps(snapshot_dict(_snap())), "utf-8")

    class Narrow(io.StringIO):
        def write(self, text: str) -> int:
            text.encode("ascii")
            return super().write(text)

    out = Narrow()
    statusline.main(root=repo, stdin=io.StringIO(""), stdout=out)
    assert out.getvalue().startswith("plumb | aligned")


def test_snapshot_counts_who_confirmed_and_the_session_intent(repo: Path, write_record,
                                                              hook_input) -> None:
    from plumb import approvals

    write_all(repo, write_record, SR1, SR2, INT1)
    core = open_core(repo)
    core.add_link("SR-002", "derives_from", __import__("plumb.contracts").contracts.Target(
        record="INT-001"))
    approvals.approve(core, ["SR-001"])
    snap = build_snapshot(open_core(repo), intent_summary="add multiply next to add")
    assert snap.confirmed_by == {"owner": 1}
    assert snap.state == "awaits you"
    # the stop hook names the intent this session works on: SR-002 derives from INT-001
    touch(repo, ".plumb/requirements/SR-002.md")
    run_stop(repo, hook_input)
    data = json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert data["intent_summary"] == "add multiply next to add"
    assert data["state"] == "awaits you"
