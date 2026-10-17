"""The band's press on a new study (SR-294): ``plumb mod room --study <slug>``, run by the
panel with its key on stdin, opens the browser room on the study (starting it when the
panel's room is not running) and marks the study opened; without the panel's key, or under the
agent's marker, nothing opens."""

from __future__ import annotations

import pytest
from mod.helpers import DIGEST, KEY, run_mod
from understand import test_intent_loop
from understand.test_intent_loop import SESSION

from plumb import study
from plumb.browser import launch
from plumb.study import cli

pytestmark = pytest.mark.sr("SR-294")

intent = test_intent_loop.intent   # INT-001, SR-040 deriving from it, and an open loop
TITLE = "How plumb's background jobs run"
ORIGIN = "http://127.0.0.1:50123"


@pytest.fixture
def announced(intent, tmp_path, monkeypatch, capsys):
    """A study added during the loop, the panel registered, and no real room or browser."""
    body = tmp_path / "body.md"
    body.write_text("A dispatcher hands each job to a worker.\n", encoding="utf-8")
    assert cli.run("study", ["add", "--title", TITLE, "--why", "the plan adds a job",
                             "--file", str(body), "--root", str(intent),
                             "--session", SESSION]) == 0
    assert run_mod(monkeypatch, capsys, intent, "hello", "--session", SESSION,
                   stdin={"key_digest": DIGEST})[0] == 0
    seen = {"started": [], "opened": [], "alive": False}
    monkeypatch.setattr(launch, "_start", lambda root, token: seen["started"].append(token)
                        or ORIGIN)
    monkeypatch.setattr(launch, "_alive", lambda origin, token: seen["alive"])
    monkeypatch.setattr(launch.webbrowser, "open", lambda url: seen["opened"].append(url))
    slug = study.studies(intent)[0]["slug"]
    return intent, slug, seen


def _room(monkeypatch, capsys, root, slug, stdin):
    return run_mod(monkeypatch, capsys, root, "room", "--study", slug, "--session", SESSION,
                   stdin=stdin)


def test_sr294_ex3_the_press_opens_the_room_on_that_study(announced, monkeypatch,
                                                          capsys) -> None:
    """SR-294 EX-3: the owner presses the line: the room starts and opens on the study."""
    root, slug, seen = announced
    code, answer, _ = _room(monkeypatch, capsys, root, slug, {"key": KEY})
    assert code == 0 and answer["origin"] == ORIGIN
    token = launch.room_token(KEY)
    assert seen["started"] == [token] and token != KEY
    assert seen["opened"] == [f"{ORIGIN}/?study={slug}#token={token}"]
    # a second press finds the panel's room running and starts none
    seen["alive"] = True
    assert _room(monkeypatch, capsys, root, slug, {"key": KEY})[0] == 0
    assert len(seen["started"]) == 1 and len(seen["opened"]) == 2


def test_sr294_ex4_the_study_opened_from_the_band_is_marked_opened(announced, monkeypatch,
                                                                    capsys) -> None:
    """SR-294 EX-4: once opened from the band, the study is no longer new (its line goes)."""
    root, slug, _ = announced
    assert study.get(root, slug)["status"] == "new"
    assert _room(monkeypatch, capsys, root, slug, {"key": KEY})[0] == 0
    assert study.get(root, slug)["status"] == "opened"


@pytest.mark.parametrize("how", ["no key", "another key", "the agent's marker"])
def test_sr294_ex2_without_the_owners_press_the_room_stays_closed(announced, monkeypatch,
                                                                  capsys, how) -> None:
    """SR-294 EX-2: only the panel's press opens the room; the study waits in it."""
    root, slug, seen = announced
    if how == "the agent's marker":
        monkeypatch.setenv("PLUMB_AGENT_SESSION", SESSION)
    stdin = {} if how == "no key" else {"key": "b2" * 32 if how == "another key" else KEY}
    assert _room(monkeypatch, capsys, root, slug, stdin)[0] == 3
    assert seen["started"] == [] and seen["opened"] == []
    assert study.get(root, slug)["status"] == "new"
