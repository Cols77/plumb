"""The hooks around intent conflicts (sp6 8.3, 8.4): the stop hook's card and stated set,
the session brief's count, the status card."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from mergedriver.mdhelpers import conflicted, parse
from iaso import cli
from iaso.hosts.claude_code import session_start, stop

pytestmark = pytest.mark.sr("SR-256")
SR = ".iaso/requirements/SR-005.md"


def _start_turn(repo: Path, session: str = "s1") -> None:
    path = repo / ".iaso" / "session" / session / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}),
                    encoding="utf-8")


def _stop(repo: Path, hook_input, session: str = "s1") -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=session, stop_hook_active=False)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=None,
                     unjudged=None) == 0
    text = out.getvalue()
    return json.loads(text).get("systemMessage", "") if text.strip() else ""


def test_owner_words_after_the_card_choose_a_side(repo: Path, hook_input) -> None:
    """End to end: the stop hook shows the card, the owner chooses at their own terminal."""
    conflicted(repo)
    _start_turn(repo)
    _stop(repo, hook_input)
    assert cli.main(["conflict", "choose", "IC-001", "--take", "feat-x",
                     "--root", str(repo)]) == 0
    assert "conflict" not in parse((repo / SR).read_text(encoding="utf-8"))[0]


def test_brief_and_status_card_count_conflicts(repo: Path, hook_input) -> None:
    conflicted(repo)
    out = io.StringIO()
    payload = hook_input("SessionStart", session_id="s2", source="startup")
    assert session_start.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                              verify=None) == 0
    assert "1 intent conflict(s) await your choice (/iaso conflicts)" in out.getvalue()
    from iaso.api import open_core
    from iaso.hosts.claude_code.snapshot import build_snapshot
    from iaso.present.render import status_card

    snapshot = build_snapshot(open_core(repo))
    assert snapshot.conflicts == 1
    assert "1 conflict awaits you" in status_card(snapshot)
    assert "1 conflict awaits you" in status_card(snapshot, ascii=True)
