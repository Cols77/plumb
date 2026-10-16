"""SP7 slice 7: the command hooks' side of the handshake with plumb's panel (sp7-owner-surface
5.1, 5.8, 5.10; sp7-realign-sp8 C7; SR-085, SR-086, SR-087, SR-116).

While the panel is active (registered and its heartbeat refreshed for this turn), the stop hook
writes ``present.json`` and prints no ``systemMessage``; with a stale heartbeat, a panel marked
off, or none, it prints as before. A block is unchanged. Session start writes ``host.json`` and
injects the brief unless the panel owns the session background. The panel's TypeScript fixtures have
the shape a real ``plumb mod draw`` answers."""

from __future__ import annotations

import io
import json
import re
import sys
import time
import types
from pathlib import Path

import pytest
from mod.helpers import DIGEST, KEY, SESSION, mod_json, run_mod, sample_card
from understand.test_read_job import make_core, open_card, record_text

from plumb.hosts.claude_code import session_start, stop
from plumb.mod import handshake

pytestmark = pytest.mark.sr("SR-266")

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


@pytest.fixture
def core(repo: Path, write_record):
    core = make_core(repo, write_record, [record_text(n) for n in range(1, 3)])
    open_card(core, sample_card(core, "SR-001"))
    return core


def _start_turn(root: Path, at: float | None = None) -> float:
    started = time.time() - 0.5 if at is None else at
    path = root / ".plumb" / "session" / SESSION / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": started, "turn_id": "t-1",
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")
    return started


def _register(monkeypatch, capsys, root: Path, *, heartbeat: float | None = None,
              **extra) -> None:
    assert run_mod(monkeypatch, capsys, root, "hello", stdin={"key_digest": DIGEST})[0] == 0
    if heartbeat is not None or extra:
        held = json.loads(mod_json(root).read_text(encoding="utf-8"))
        if heartbeat is not None:
            held["heartbeat"] = _iso(heartbeat)
        held.update(extra)
        mod_json(root).write_text(json.dumps(held), encoding="utf-8")


def _stop(root: Path, hook_input) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=SESSION, stop_hook_active=False)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=root, verify=None,
                     unjudged=None) == 0
    return out.getvalue()


def _present(root: Path) -> dict | None:
    path = handshake.present_path(root, SESSION)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ---------------------------------------------------------------- stop: present.json


def test_stop_writes_present_json_and_no_system_message_while_the_panel_is_active(
        core, monkeypatch, capsys, hook_input) -> None:
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    out = _stop(core.root, hook_input)
    # the owner's decision (2026-10-14): one plumb line instead of silence (SR-159 EX-1)
    assert json.loads(out) == {"systemMessage": "plumb: 1 new card waits on the panel"}
    present = _present(core.root)
    assert present is not None
    assert {"turn", "confirmations", "cards"} <= set(present)
    assert "settled" not in present and "settled_records" not in present
    assert present["turn"] == int(started) and present["session"] == SESSION
    assert present["turn_id"] == "t-1" and present["written_at"]
    # the cards the end-of-turn text drew (slice 3), each with its full content (SR-116)
    by_id = {c["id"]: c for c in present["cards"]}
    card = by_id["card:SR-001"]
    assert all(c["content"] and c["content"]["id"] == c["id"] for c in present["cards"])
    assert card["id"] == "card:SR-001" and card["kind"] == "trial"
    assert card["status"] == "open" and card["questions"][0]["record"] == "SR-001"


def test_stop_prints_as_before_when_the_heartbeat_is_older_than_the_turn(
        core, monkeypatch, capsys, hook_input) -> None:
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root,
              heartbeat=started - handshake.HEARTBEAT_SLACK_S - 60)
    out = _stop(core.root, hook_input)
    message = json.loads(out)["systemMessage"]
    assert "Requirement 1" in message               # the card, as text
    assert _present(core.root) is None


def test_stop_prints_as_before_without_a_panel_or_with_the_panel_off(
        core, monkeypatch, capsys, hook_input) -> None:
    started = _start_turn(core.root)
    assert json.loads(_stop(core.root, hook_input))["systemMessage"]
    assert _present(core.root) is None
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2, active=False)
    assert json.loads(_stop(core.root, hook_input))["systemMessage"]
    assert _present(core.root) is None


def test_a_block_is_unchanged_while_the_panel_is_active(core, monkeypatch, capsys) -> None:
    from plumb.hosts.claude_code.hookio import HookOutput

    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    ctx = types.SimpleNamespace(root=core.root, session_id=SESSION, extra={})
    block = HookOutput(block_reason="plumb: run the covering tests")
    assert handshake.deliver(ctx, block) is block
    assert _present(core.root) is None
    shown = HookOutput(system_message="plumb: a card")
    line = handshake.deliver(ctx, shown)      # one plumb line, not the card (SR-159 EX-1)
    assert line is not None and line.system_message == "plumb: 1 new card waits on the panel"
    assert "a card" not in line.system_message and _present(core.root) is not None


# ---------------------------------------------------------------- session start


def _session_start(root: Path, hook_input) -> str:
    out = io.StringIO()
    payload = hook_input("SessionStart", session_id=SESSION, source="startup")
    assert session_start.main(stdin=io.StringIO(payload), stdout=out, root=root,
                              verify=None) == 0
    return out.getvalue()


def _brief(root: Path) -> dict:
    return json.loads((root / ".plumb" / "session" / SESSION / "brief.json")
                      .read_text(encoding="utf-8"))


def test_session_start_injects_the_brief_and_says_so_unless_the_panel_owns_it(
        core, monkeypatch, capsys, hook_input) -> None:
    out = _session_start(core.root, hook_input)
    assert out.strip()                                     # the brief, as today
    assert _brief(core.root) == {"injected": True}
    host = json.loads((core.root / ".plumb" / "session" / SESSION / "host.json")
                      .read_text(encoding="utf-8"))
    assert host["python"] == sys.executable


@pytest.mark.sr("SR-266")
def test_session_start_still_gives_the_agent_the_brief_when_the_panel_gives_the_background(
        core, monkeypatch, capsys, hook_input) -> None:
    """SR-173 EX-1: the panel is the owner's surface; the agent's channel keeps the brief."""
    _register(monkeypatch, capsys, core.root, background=True)
    out = _session_start(core.root, hook_input)
    assert out.strip().startswith("plumb brief")
    assert _brief(core.root) == {"injected": True}


def test_a_registered_panel_without_the_background_leaves_the_brief_in(
        core, monkeypatch, capsys, hook_input) -> None:
    _register(monkeypatch, capsys, core.root)
    assert _session_start(core.root, hook_input).strip()
    assert _brief(core.root) == {"injected": True}


# ---------------------------------------------------------------- SR-116 content on draw


def test_draw_carries_the_full_card_content_where_plumb_derives_it(core, monkeypatch,
                                                                  capsys) -> None:
    """SR-116 on the panel: every card's ``content`` is the end-of-turn full card
    (``understand.fullcard``), for a stale link and for a card plumb built alike."""
    from plumb import stale
    from plumb.understand import fullcard

    stale.add_card(core.root, SESSION, link="SR-001#0", record="SR-001", path="src/a.py",
                   topic="Adds numbers", issue="the code it is linked to changed",
                   options=["re-pin it", "reword it"], recommended=0, turn=1)
    monkeypatch.setattr(fullcard, "stale_content", lambda core, entry, session="": {
        "context": ["add returns the sum"], "link": entry["link"]})
    _register(monkeypatch, capsys, core.root)
    code, answer, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0
    by_id = {c["id"]: c for c in answer["cards"]}
    assert by_id["stale:SR-001#0"]["content"] == {
        "context": ["add returns the sum"], "link": "SR-001#0"}
    shown = by_id["card:SR-001"]["content"]
    assert shown["kind"] == "trial"
    assert shown["options"] and all("consequence" in o for o in shown["options"])
    assert {"topic", "issue", "context", "assumptions", "wont", "diagram"} <= set(shown)


# ---------------------------------------------------------------- the panel's fixtures


def _fixture(name: str) -> object:
    fixtures = PLUGIN.parent / "tests" / "plugin" / "mod" / "fixtures.ts"   # SR-123: not shipped
    text = fixtures.read_text(encoding="utf-8")
    found = re.search(rf"// BEGIN {name}\n.*?= (.*?)\n// END {name}", text, re.S)
    assert found, name
    return json.loads(found.group(1))


def test_the_panel_fixtures_have_the_shape_of_a_real_draw_and_present(
        core, monkeypatch, capsys, hook_input) -> None:
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    _stop(core.root, hook_input)
    code, drawn, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 0
    real_card = drawn["cards"][0]
    fixture = _fixture("DRAW")
    assert set(fixture) == set(drawn)
    for card in fixture["cards"]:
        assert set(card) == set(real_card)
        for offer in card["offers"]:
            assert set(offer) == set(real_card["offers"][0])
            for button in offer["buttons"]:
                assert set(button) == set(real_card["offers"][0]["buttons"][0])
    assert set(_fixture("PRESENT")) == set(_present(core.root))
    code, pressed, _ = run_mod(monkeypatch, capsys, core.root, "press", "--offer",
                               real_card["offers"][0]["offer_id"], "--choice", "3",
                               stdin={"key": KEY})
    assert code == 0 and set(_fixture("PRESS_LEAVE_OPEN")) == set(pressed)
