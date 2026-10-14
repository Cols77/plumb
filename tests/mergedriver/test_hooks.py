"""The hooks around intent conflicts (sp6 8.3, 8.4): the stop hook's card and stated set,
the session brief's count, the status card."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from mergedriver.mdhelpers import conflicted, log_prompt, parse
from plumb import cli
from plumb.hosts.claude_code import session_start, stop

pytestmark = pytest.mark.sr("SR-076")
SR = ".plumb/requirements/SR-005.md"


def _start_turn(repo: Path, session: str = "s1") -> None:
    path = repo / ".plumb" / "session" / session / "turn.json"
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


def _stated(repo: Path) -> dict:
    return json.loads((repo / ".plumb" / "session" / "stated.json").read_text("utf-8"))


def test_stop_shows_a_new_conflict_once_and_states_it(repo: Path, hook_input) -> None:
    conflicted(repo)
    _start_turn(repo)
    head = ["relay checks", "main and feat-x changed it in different ways"]
    first = _stop(repo, hook_input)
    assert first.splitlines()[:2] == head
    assert ("main says: What it says: A relay pins only the records the owner's "
            "words affirm. / feat-x says: What it says: A relay pins the stated group, named by "
            "its title.") in first.splitlines()
    assert [c["ic"] for c in _stated(repo)["conflicts"]] == ["IC-001"]
    # SR-012 with DEC-034 replaced "once per version": a card that still asks the owner is
    # drawn at the end of every turn while the conflict is open, and stays stated
    _start_turn(repo)
    assert _stop(repo, hook_input).splitlines()[:2] == head
    assert [c["ic"] for c in _stated(repo)["conflicts"]] == ["IC-001"]
    _start_turn(repo)
    assert cli.main(["conflicts", "--root", str(repo)]) == 0  # /plumb conflicts asks again
    assert _stop(repo, hook_input).splitlines()[:2] == head
    assert [c["ic"] for c in _stated(repo)["conflicts"]] == ["IC-001"]


def test_owner_words_after_the_card_choose_a_side(repo: Path, hook_input) -> None:
    """End to end: the stop hook shows the card, the owner says "keep feat-x's version",
    the agent relays it."""
    conflicted(repo)
    _start_turn(repo)
    _stop(repo, hook_input)
    later = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5))
    digest = log_prompt(repo, "keep feat-x's version", at=later)
    assert cli.main(["conflict", "relay", "IC-001", "--take", "feat-x", "--prompt", digest,
                     "--quote", "keep feat-x's version", "--root", str(repo)]) == 0
    assert "conflict" not in parse((repo / SR).read_text(encoding="utf-8"))[0]


def test_brief_and_status_card_count_conflicts(repo: Path, hook_input) -> None:
    conflicted(repo)
    out = io.StringIO()
    payload = hook_input("SessionStart", session_id="s2", source="startup")
    assert session_start.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                              verify=None) == 0
    assert "1 intent conflict(s) await your choice (/plumb conflicts)" in out.getvalue()
    from plumb.api import open_core
    from plumb.hosts.claude_code.snapshot import build_snapshot
    from plumb.present.render import status_card

    snapshot = build_snapshot(open_core(repo))
    assert snapshot.conflicts == 1
    assert "1 conflict awaits you" in status_card(snapshot)
    assert "1 conflict awaits you" in status_card(snapshot, ascii=True)
