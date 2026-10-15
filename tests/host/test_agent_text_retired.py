"""SR-173 EX-3: the full/compact/off intent-card setting is retired."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb.hosts.claude_code import session_start

pytestmark = pytest.mark.sr("SR-173")


def _start(repo: Path, hook_input) -> str:
    out = io.StringIO()
    assert session_start.main(stdin=io.StringIO(hook_input("SessionStart", source="startup")),
                              stdout=out, root=repo, verify=FakeVerify()) == 0
    return out.getvalue()


def test_a_set_card_mode_has_no_effect_and_plumb_says_it_is_retired(
        repo: Path, hook_input) -> None:
    assert "retired" not in _start(repo, hook_input)
    (repo / ".plumb" / "config.yaml").write_text("present:\n  card: full\n", "utf-8")
    out = _start(repo, hook_input)
    assert "plumb: the card setting (full, compact, off) is retired" in out
    assert out.count("is retired") == 1
    import json

    status = json.loads((repo / ".plumb" / "session" / "status.json").read_text("utf-8"))
    assert "card" not in status.get("present", {})
