"""SR-442 EX-1: the Codex parity review names the Claude UI runtime dependency and claims no
verified Codex mod."""

from pathlib import Path

import pytest

REVIEW = Path(__file__).resolve().parents[2] / "docs" / "codex-parity-review.md"


@pytest.mark.sr("SR-442")
def test_sr442_ex1_the_review_names_the_ui_dependency_and_claims_no_verified_mod() -> None:
    text = " ".join(REVIEW.read_text(encoding="utf-8").split())
    assert "imports atom/read/update/Register from claude-code" in text     # the dependency
    assert "No documented equivalent Codex UI module API established" in text
    assert "not a verified Codex mod" in text       # no live mod is claimed
