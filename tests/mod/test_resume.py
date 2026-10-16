"""A resumed session gets its panel back (SR-126, the panel staying off after ``claude
--resume``): the session id is the same, the new panel process has a new key, and the old
``mod.json`` would refuse its hello for ever and keep the brief out. The session-start hook of
a resumed session retires the old registration (also under the marker a resumed hook inherits); the new
panel's hello then replaces it, the brief goes in until it does, and a button approval pressed
before or after the resume still re-checks."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from understand.test_read_job import make_core, open_card, record_text

from mod.helpers import DIGEST, KEY, OTHER_KEY, SESSION, kinds, mod_json, run_mod, sample_card
from plumb import confirm
from plumb.api import open_core
from plumb.hosts.claude_code import hookio, session_start
from plumb.mod import handshake
from plumb.mod import session as mod_session

pytestmark = pytest.mark.sr("SR-264")

NEW_DIGEST = mod_session.key_digest(OTHER_KEY)
CONFIRM = 0


@pytest.fixture
def core(repo: Path, write_record):
    core = make_core(repo, write_record, [record_text(n) for n in range(1, 4)])
    open_card(core, sample_card(core, "SR-001"))
    open_card(core, sample_card(core, "SR-002"))
    return core


def _start(root: Path, hook_input, source: str) -> str:
    out = io.StringIO()
    payload = hook_input("SessionStart", session_id=SESSION, source=source)
    assert session_start.main(stdin=io.StringIO(payload), stdout=out, root=root,
                              verify=None) == 0
    return out.getvalue()


def _hello(monkeypatch, capsys, root: Path, digest: str) -> tuple[int, str]:
    code, _, err = run_mod(monkeypatch, capsys, root, "hello", stdin={"key_digest": digest})
    return code, err


def _press_first(monkeypatch, capsys, root: Path, key: str, card: str) -> dict:
    code, answer, _ = run_mod(monkeypatch, capsys, root, "draw", stdin={"key": key})
    assert code == 0
    (drawn,) = [c for c in answer["cards"] if c["id"] == card]
    offer = drawn["offers"][0]["offer_id"]
    code, answer, err = run_mod(monkeypatch, capsys, root, "press", "--offer", offer,
                                "--choice", str(CONFIRM), stdin={"key": key})
    assert code == 0, err
    return answer


def test_resume_retires_the_old_panel_and_the_new_one_registers(core, monkeypatch, capsys,
                                                                hook_input) -> None:
    assert _hello(monkeypatch, capsys, core.root, DIGEST)[0] == 0
    held = json.loads(mod_json(core.root).read_text(encoding="utf-8"))
    held["background"] = True
    mod_json(core.root).write_text(json.dumps(held), encoding="utf-8")
    # before the resume's start, a second hello is still refused
    code, err = _hello(monkeypatch, capsys, core.root, NEW_DIGEST)
    assert code == 3 and "already has its panel" in err
    out = _start(core.root, hook_input, "resume")
    assert out.strip()                                  # nobody owns the background: the brief
    assert json.loads((core.root / ".plumb" / "session" / SESSION / "brief.json")
                      .read_text(encoding="utf-8")) == {"injected": True}
    assert _hello(monkeypatch, capsys, core.root, NEW_DIGEST)[0] == 0
    held = json.loads(mod_json(core.root).read_text(encoding="utf-8"))
    assert held["key_digest"] == NEW_DIGEST and held["active"] is True
    assert held["earlier"] == [DIGEST]
    assert kinds(core.root).count("mod-hello") == 2
    # registered again: a third hello is refused as before
    assert _hello(monkeypatch, capsys, core.root, DIGEST)[0] == 3


@pytest.mark.parametrize("source", ["startup", "clear", "compact"])
def test_only_a_resume_retires(core, monkeypatch, capsys, hook_input, source: str) -> None:
    assert _hello(monkeypatch, capsys, core.root, DIGEST)[0] == 0
    _start(core.root, hook_input, source)
    assert _hello(monkeypatch, capsys, core.root, NEW_DIGEST)[0] == 3


def test_a_resume_start_under_the_agent_marker_still_retires(core, monkeypatch, capsys,
                                                             hook_input) -> None:
    """The first start exported the marker into the session env; the resume's hook has it."""
    assert _hello(monkeypatch, capsys, core.root, DIGEST)[0] == 0
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "claude-code")
    _start(core.root, hook_input, "resume")
    monkeypatch.delenv("PLUMB_AGENT_SESSION")
    assert _hello(monkeypatch, capsys, core.root, NEW_DIGEST)[0] == 0
    assert json.loads(mod_json(core.root).read_text(encoding="utf-8"))["earlier"] == [DIGEST]


def test_presses_before_and_after_the_resume_both_recheck(core, monkeypatch, capsys,
                                                          hook_input) -> None:
    assert _hello(monkeypatch, capsys, core.root, DIGEST)[0] == 0
    _press_first(monkeypatch, capsys, core.root, KEY, "card:SR-001")
    _start(core.root, hook_input, "resume")
    assert _hello(monkeypatch, capsys, core.root, NEW_DIGEST)[0] == 0
    # the old key no longer presses
    code, _, _ = run_mod(monkeypatch, capsys, core.root, "draw", stdin={"key": KEY})
    assert code == 3
    answer = _press_first(monkeypatch, capsys, core.root, OTHER_KEY, "card:SR-002")
    assert answer["confirmed"] == ["SR-002"]
    fresh = open_core(core.root)
    approvals = [e for e in fresh.events() if e.kind == "approval"]
    assert [a.payload["key_digest"] for a in approvals] == [DIGEST, NEW_DIGEST]
    for approval in approvals:
        assert confirm.entry_problem(approval, set(), (), fresh) is None


def test_a_cut_prints_nothing_while_the_panel_owns_the_background(core, monkeypatch, capsys,
                                                                  hook_input) -> None:
    """Nothing was owed: the watchdog's cut prints no skip notice either."""
    assert _hello(monkeypatch, capsys, core.root, DIGEST)[0] == 0
    held = json.loads(mod_json(core.root).read_text(encoding="utf-8"))
    mod_json(core.root).write_text(json.dumps({**held, "background": True}), encoding="utf-8")
    kept = hookio.Kept()
    ctx = hookio.HookContext("session-start", {"source": "startup"}, core.root, SESSION,
                             hookio.Deadline(800, None), kept=kept)
    assert handshake.session_start(ctx) is True
    assert hookio._cut_output(kept, hookio.SKIP_BUDGET, True) == ""


def test_a_broken_panel_file_keeps_the_brief(core, monkeypatch, hook_input) -> None:
    def broken(ctx):
        raise ValueError("a malformed mod.json")

    monkeypatch.setattr(handshake, "session_start", broken)
    assert _start(core.root, hook_input, "startup").strip()
