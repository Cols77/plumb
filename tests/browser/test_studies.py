"""The room's Studies section and Understanding page (SR-292, SR-294; DEC-151, DEC-152): it
lists the studies, opens one, takes 'I know this' / 'Go deeper' and the owner's edit of the
picture; it never opens by itself, and its buttons never reach a session."""

import threading
import webbrowser

import pytest
from study.helpers import written
from understand import test_intent_loop
from understand.test_intent_loop import SESSION

from iaso import study
from iaso.api import open_core

from .test_server import auth, request

pytestmark = pytest.mark.sr("SR-294")

intent = test_intent_loop.intent   # INT-001, SR-040 deriving from it, and an open loop
TITLE = "How iaso's background jobs run"


@pytest.fixture
def room(intent, tmp_path, monkeypatch):
    """A study added during the loop, then the room's server (not a browser)."""
    from iaso.browser.server import make_server
    from iaso.browser.service import BrowserService

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: opened.append(a))
    body = tmp_path / "body.md"
    body.write_text("A dispatcher hands each job to a worker.\n", encoding="utf-8")
    assert written(intent, SESSION, TITLE, "the plan adds a job", body, topic="hooks") == 0
    httpd = make_server(BrowserService(intent), port=0, token="test-token")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, opened
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def _json(server, method, path, data=None):
    import json

    status, body, _ = request(server, method, path, data, **auth(server))
    assert status == 200, body
    return json.loads(body)


def test_sr294_ex2_an_announced_study_waits_in_the_closed_room(room):
    """SR-294 EX-2: the owner does nothing: the room stays closed and the study waits in it."""
    server, opened = room
    assert opened == []
    [listed] = _json(server, "GET", "/api/studies")["studies"]
    assert (listed["title"], listed["status"]) == (TITLE, "new")
    assert "body" not in listed


def test_sr294_ex3_reading_the_study_opens_it(room):
    """SR-294 EX-3: the owner reads the study in the room: it is opened, no longer new (the
    band's study line goes; tests/plugin/mod/categories.test.tsx draws that side)."""
    server, _ = room
    slug = study.studies(server.service.root)[0]["slug"]
    read = _json(server, "POST", f"/api/studies/{slug}/open", {})
    assert read["status"] == "opened" and "dispatcher" in read["body"]
    assert [s["status"] for s in _json(server, "GET", "/api/studies")["studies"]] == ["opened"]


@pytest.mark.sr("SR-292")
def test_sr292_ex3_removing_a_line_in_the_room(room):
    """SR-292 EX-3: the owner removes 'knows: hooks' on the Understanding page: the picture no
    longer says so, and hooks studies are candidates again."""
    server, _ = room
    slug = study.studies(server.service.root)[0]["slug"]
    marked = _json(server, "POST", f"/api/studies/{slug}/mark", {"mark": "known"})
    assert marked["understanding"]["knows"] == ["hooks"]
    assert study.knows(server.service.root, "hooks")
    saved = _json(server, "POST", "/api/understanding", {"text": "- needs: the judge\n"})
    assert (saved["knows"], saved["needs"]) == ([], ["the judge"])
    assert not study.knows(server.service.root, "hooks")
    assert _json(server, "GET", "/api/studies")["understanding"]["text"] == "- needs: the judge\n"


@pytest.mark.sr("SR-292")
def test_the_study_buttons_never_reach_a_session(room):
    """DEC-152: 'I know this' and 'Go deeper' correct the picture only: no follow-up, no card
    press, nothing written under the sessions."""
    server, _ = room
    root = server.service.root
    sessions = root / ".iaso" / "session"
    before = {p: p.read_bytes() for p in sessions.rglob("*") if p.is_file()}
    events = len(open_core(root).events())
    slug = study.studies(root)[0]["slug"]
    for how in ("deeper", "known"):
        _json(server, "POST", f"/api/studies/{slug}/mark", {"mark": how})
    assert {p: p.read_bytes() for p in sessions.rglob("*") if p.is_file()} == before
    assert len(open_core(root).events()) == events


def test_room_refuses_bad_study_requests(room):
    server, _ = room
    slug = study.studies(server.service.root)[0]["slug"]
    assert request(server, "POST", "/api/studies/no-such/open", {}, **auth(server))[0] == 404
    assert request(server, "POST", f"/api/studies/{slug}/mark", {"mark": "accepted"},
                   **auth(server))[0] == 400
    assert request(server, "POST", "/api/understanding", {"text": 3}, **auth(server))[0] == 400
    assert request(server, "GET", "/api/studies")[0] == 401
