"""The room plays a study's ready clips (SR-319, SR-365, SR-370): only the committed mp4 and vtt
of a clip that is ready, never a path from the study itself; a missing file is a 404 the room
turns into a fallback line at the clip's place."""

import json
import re
import threading

import pytest
from study.helpers import written
from understand import test_intent_loop
from understand.test_intent_loop import SESSION

from plumb import study

from .test_server import auth, request

intent = test_intent_loop.intent


@pytest.fixture
def room(intent, tmp_path):
    """A written study 'slug', and the room's server (not a browser)."""
    from plumb.browser.server import make_server
    from plumb.browser.service import BrowserService

    body = tmp_path / "body.md"
    body.write_text("A dispatcher hands each job to a worker.\n", encoding="utf-8")
    assert written(intent, SESSION, "How the judge cascade runs", "the plan adds it", body) == 0
    slug = study.studies(intent)[0]["slug"]
    httpd = make_server(BrowserService(intent), port=0, token="test-token")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, intent, slug
    httpd.shutdown()
    httpd.server_close()
    thread.join()


CLIP = "cascade"


def _video(root, slug, state, extra=""):
    """Set the state of the study's clip 'cascade' in its frontmatter."""
    path = study.folder(root) / f"{slug}.md"
    text = re.sub(r"^clips: .*\n", "", path.read_text(encoding="utf-8"), flags=re.M)
    clips = json.dumps({CLIP: {"state": state, "reason": "", "revisions": 0}})
    path.write_text(text.replace("\n---\n", f"\nclips: {clips}\n{extra}---\n", 1),
                    encoding="utf-8")


def _media(root, slug, suffix):
    return study.folder(root) / f"{slug}.{CLIP}{suffix}"


def _get(server, slug, kind, clip=CLIP):
    return request(server, "GET", f"/api/studies/{slug}/media/{clip}/{kind}", **auth(server))


@pytest.mark.sr("SR-319")
def test_sr319_ex1_a_ready_study_serves_its_mp4_and_carries_the_state(room):
    """SR-319 EX-1: the room gets the video bytes and the study says video is ready."""
    server, root, slug = room
    _media(root, slug, ".mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    _video(root, slug, "ready")
    status, body, headers = _get(server, slug, "video")
    assert (status, body) == (200, b"\x00\x00\x00\x18ftypmp42")
    assert headers["Content-Type"] == "video/mp4"
    _, opened, _ = request(server, "POST", f"/api/studies/{slug}/open", {}, **auth(server))
    assert json.loads(opened)["clips"][CLIP]["state"] == "ready"


@pytest.mark.sr("SR-319")
def test_sr319_ex2_a_missing_mp4_is_a_404_and_the_text_still_opens(room):
    """SR-319 EX-2: no file behind a ready video: 404, the study itself still opens."""
    server, root, slug = room
    _video(root, slug, "ready")
    assert _get(server, slug, "video")[0] == 404
    assert request(server, "POST", f"/api/studies/{slug}/open", {}, **auth(server))[0] == 200


@pytest.mark.sr("SR-319")
@pytest.mark.parametrize("state", ["", "rendering", "checking", "failed"])
def test_sr319_ex3_only_a_ready_video_is_served_and_no_path_comes_from_the_study(
        room, tmp_path, state):
    """SR-319 EX-3: a study naming a path outside the project, or one not ready: nothing served."""
    server, root, slug = room
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"secret")
    _media(root, slug, ".mp4").write_bytes(b"mp4")
    _video(root, slug, state, f'video_path: "{outside.as_posix()}"\n')
    assert _get(server, slug, "video")[0] == 404
    _video(root, slug, "ready", f'video_path: "{outside.as_posix()}"\n')
    assert _get(server, slug, "video")[1] == b"mp4"
    assert _get(server, "..%2Fx", "video")[0] == 404
    assert _get(server, slug, "video", clip="..%2Fx")[0] == 404
    assert _get(server, slug, "video", clip="other")[0] == 404     # a clip with no state


@pytest.mark.sr("SR-365")
def test_sr365_ex2_the_track_is_served_as_text_vtt(room):
    """SR-365 EX-2: the room can load the cues as a subtitle track."""
    server, root, slug = room
    _media(root, slug, ".vtt").write_text("WEBVTT\n\n00:00.000 --> 00:04.000\nHi\n",
                                                    encoding="utf-8")
    _video(root, slug, "ready")
    status, body, headers = _get(server, slug, "subtitles")
    assert status == 200 and body.startswith(b"WEBVTT")
    assert headers["Content-Type"].startswith("text/vtt")


@pytest.mark.sr("SR-365")
def test_sr365_ex4_a_missing_vtt_is_a_404_while_the_video_still_plays(room):
    """SR-365 EX-4: no .vtt: the subtitles 404 (the room says so) and the video is served."""
    server, root, slug = room
    _media(root, slug, ".mp4").write_bytes(b"mp4")
    _video(root, slug, "ready")
    assert _get(server, slug, "subtitles")[0] == 404
    assert _get(server, slug, "video")[0] == 200


@pytest.mark.sr("SR-319")
def test_sr319_the_media_route_needs_the_capability(room):
    """The same guard as the rest of the API."""
    server, _, slug = room
    assert request(server, "GET", f"/api/studies/{slug}/media/{CLIP}/video")[0] == 401
