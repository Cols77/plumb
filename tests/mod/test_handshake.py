"""SP7 slice 7: the command hooks' side of the handshake with plumb's panel (sp7-owner-surface
5.1, 5.8, 5.10; sp7-realign-sp8 C7; SR-085, SR-086, SR-087, SR-116).

While the panel is active (registered and its heartbeat refreshed for this turn), the stop hook
writes ``present.json`` and prints no ``systemMessage``; with a stale heartbeat, a panel marked
off, or none, it prints as before. A block is unchanged. Session start writes ``host.json`` and
injects the brief unless the panel owns the session background."""

from __future__ import annotations

import io
import json
import sys
import time
import types
from pathlib import Path

import pytest
from mod.helpers import DIGEST, SESSION, mod_json, run_mod, sample_card
from understand.test_read_job import make_core, open_card, record_text

from plumb.hosts.claude_code import session_start, stop
from plumb.mod import handshake

pytestmark = pytest.mark.sr("SR-266")


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
    # the same as without a panel (SR-265): a waiting card is no plumb line (SR-363)
    assert out == ""
    present = _present(core.root)
    assert present is not None
    assert {"turn", "confirmations"} <= set(present) and "cards" not in present
    assert "settled" not in present and "settled_records" not in present
    assert present["turn"] == int(started) and present["session"] == SESSION
    assert present["turn_id"] == "t-1" and present["written_at"]


def test_stop_prints_as_before_when_the_heartbeat_is_older_than_the_turn(
        core, monkeypatch, capsys, hook_input) -> None:
    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root,
              heartbeat=started - handshake.HEARTBEAT_SLACK_S - 60)
    out = _stop(core.root, hook_input)
    assert out == ""                                     # SR-363: no question count
    assert _present(core.root) is None


def test_stop_prints_as_before_without_a_panel_or_with_the_panel_off(
        core, monkeypatch, capsys, hook_input) -> None:
    started = _start_turn(core.root)
    assert _stop(core.root, hook_input) == ""            # SR-363: no question count
    assert _present(core.root) is None
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2, active=False)
    _stop(core.root, hook_input)
    assert _present(core.root) is None


def test_a_block_is_unchanged_while_the_panel_is_active(core, monkeypatch, capsys) -> None:
    from plumb.hosts.claude_code.hookio import HookOutput

    started = _start_turn(core.root)
    _register(monkeypatch, capsys, core.root, heartbeat=started + 0.2)
    ctx = types.SimpleNamespace(root=core.root, session_id=SESSION, extra={})
    block = HookOutput(block_reason="plumb: run the covering tests")
    assert handshake.deliver(ctx, block) is block
    assert _present(core.root) is None
    line = HookOutput(system_message="plumb: your answer on deadline reminders was applied")
    assert handshake.deliver(ctx, line) is line      # the stop's own line (SR-265)
    assert _present(core.root) is not None


# ---------------------------------------------------------------- session start


def _session_start(root: Path, hook_input) -> str:
    # every record new since the last brief, so the brief has a line to say (SR-374 EX-9)
    (root / ".plumb" / "session").mkdir(parents=True, exist_ok=True)
    (root / ".plumb" / "session" / "brief_seen.json").write_text("{}", "utf-8")
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
    assert out.strip().startswith("plumb: changed since you last looked")
    assert _brief(core.root) == {"injected": True}


def test_a_registered_panel_without_the_background_leaves_the_brief_in(
        core, monkeypatch, capsys, hook_input) -> None:
    _register(monkeypatch, capsys, core.root)
    assert _session_start(core.root, hook_input).strip()
    assert _brief(core.root) == {"injected": True}


# ---------------------------------------------------------------- SR-116 content on draw


# ---------------------------------------------------------------- the panel's fixtures


