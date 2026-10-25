"""Video clips that teach (SR-316, SR-318, SR-364, SR-365, SR-366, SR-370; INT-093, INT-111):
the mix the body composes, the storyboard first, the background render, the subtitle track, the
reviewer's frame check."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from understand.test_intent_loop import SESSION

from plumb import study
from plumb.study import cli, video

TITLE = "How the judge cascade runs"
SLUG = "how-the-judge-cascade-runs"
CLIP = "cascade"
BODY = "The cascade asks the judges in turn.\n\n```video\ncascade\n```\n\nThen it builds.\n"
SCENE = "from manim import *\n\nclass S(Scene):\n    def construct(self):\n        self.wait(1)\n"


def _board(**over: Any) -> dict[str, Any]:
    beats = [{"shows": "the cascade among the stages",
              "subtitle": "The cascade sits between clarify and build.", "seconds": 4},
             {"shows": "the three judges", "subtitle": "Three judges look in turn.", "seconds": 3},
             {"shows": "the recap and the text",
              "subtitle": "So: where it sits, what it decides. Read the text.", "seconds": 4,
              "recap": True}]
    return {"question": "How does the cascade run?", "goals": ["where it sits", "what it decides"],
            "context": "Stage II of the intent loop; SR-210", "beats": beats, **over}


def _study(repo: Path, *argv: str) -> int:
    return cli.run("study", [*argv, "--root", str(repo), "--session", SESSION])


def _file(tmp_path: Path, name: str, text: str) -> str:
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return str(f)


def _fake_mp4(path: Path, seconds: int = 4) -> Path:
    import av

    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=5)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for _ in range(seconds * 5):
            for packet in stream.encode(av.VideoFrame(64, 48, "yuv420p")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path


def _accept(repo: Path, body: str = BODY) -> Path:
    assert _study(repo, "propose", "--title", TITLE, "--why", "the owner asked",
                  "--depth", "video", "--asked") == 0
    study.choose(repo, SLUG, "video")
    study.add(repo, SLUG, body)
    return repo


@pytest.fixture
def accepted(repo: Path) -> Path:
    return _accept(repo)


def _state(repo: Path, key: str = "state") -> Any:
    return ((study.get(repo, SLUG).get("clips") or {}).get(CLIP) or {}).get(key, "")


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """``render`` starts no process; the test runs the job itself."""
    calls: list[Any] = []
    real = video.subprocess.Popen

    def popen(cmd: list[str], *a: Any, **k: Any) -> Any:
        if "render-job" not in cmd:     # manim's own run goes through
            return real(cmd, *a, **k)
        calls.append(cmd)

    monkeypatch.setattr(video.subprocess, "Popen", popen)
    return calls


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(video, "run_manim", lambda scene, media: _fake_mp4(media / "made.mp4"))


def _render(repo: Path, tmp_path: Path, board: dict[str, Any] | None = None) -> int:
    assert _study(repo, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(board or _board()))) == 0
    return _study(repo, "render", SLUG, "--clip", CLIP, "--scene", _file(tmp_path, "f.py", SCENE))


def _rendered(repo: Path, tmp_path: Path) -> None:
    assert _render(repo, tmp_path) == 0
    video.job(repo, SLUG, CLIP)


# ------------------------------------------------------------------------ SR-316


@pytest.mark.sr("SR-316")
def test_sr316_ex1_render_starts_in_the_background_and_the_turn_does_not_wait(
        accepted: Path, tmp_path: Path, popen: list[Any]) -> None:
    assert _render(accepted, tmp_path) == 0
    assert _state(accepted) == "rendering" and study.get(accepted, SLUG)["depth"] == "video"
    [cmd] = popen
    assert cmd[:3] == [sys.executable, "-m", "plumb"] and "render-job" in cmd
    assert video.path(accepted, SLUG, CLIP, ".py").read_text(encoding="utf-8") == SCENE


@pytest.mark.sr("SR-316")
def test_sr316_ex2_a_passed_check_shows_the_video(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    _rendered(accepted, tmp_path)
    assert _state(accepted) == "checking"
    assert _study(accepted, "check", SLUG, "--clip", CLIP, "--pass", "--reviewer", "agent-2") == 0
    assert _state(accepted) == "ready"


@pytest.mark.sr("SR-316")
def test_sr316_ex3_a_scene_error_keeps_the_text_says_why_and_retries_nothing(
        accepted: Path, tmp_path: Path, popen: list[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(scene: Path, media: Path) -> Path:
        raise RuntimeError("NameError: name 'Foo' is not defined")

    monkeypatch.setattr(video, "run_manim", broken)
    assert _render(accepted, tmp_path) == 0
    video.job(accepted, SLUG, CLIP)
    assert _state(accepted) == "failed" and "NameError" in _state(accepted, "reason")
    assert len(popen) == 1


@pytest.mark.sr("SR-316")
def test_sr316_ex4_other_depths_start_no_render(
        repo: Path, tmp_path: Path, popen: list[Any]) -> None:
    for depth in ("md", "diagrams"):
        slug = study.propose(repo, title=f"A {depth} study", why="w", depth=depth, loop="l",
                             step="s", asked=True)
        assert study.choose(repo, slug, depth)["status"] == "accepted"
        study.add(repo, slug, "Text.")
        with pytest.raises(ValueError, match="depth video"):
            video.render(repo, slug, CLIP, Path(_file(tmp_path, "x.py", SCENE)))
    assert popen == []


@pytest.mark.sr("SR-316")
def test_sr316_ex5_a_real_render_of_plain_text_without_latex(
        accepted: Path, tmp_path: Path, popen: list[Any]) -> None:
    scene = ("from manim import *\n\nclass S(Scene):\n    def construct(self):\n"
             "        for word in ('one', 'two'):\n"
             "            self.add(Text(word))\n            self.wait(1)\n"
             "            self.clear()\n")
    board = _board(beats=[
        {"shows": "one", "subtitle": "First.", "seconds": 1.5},
        {"shows": "two", "subtitle": "Second.", "seconds": 1.5},
        {"shows": "the recap", "subtitle": "Recap.", "seconds": 1.5, "recap": True}])
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(board))) == 0
    assert _study(accepted, "render", SLUG, "--clip", CLIP, "--scene", _file(tmp_path, "f.py", scene)) == 0
    video.job(accepted, SLUG, CLIP)       # the real Manim
    assert _state(accepted) == "checking", _state(accepted, "reason")
    assert video.path(accepted, SLUG, CLIP, ".mp4").stat().st_size > 0
    assert video.path(accepted, SLUG, CLIP, ".vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    assert len(list(video.frames_dir(accepted, SLUG, CLIP).glob("*.png"))) == 4


# ------------------------------------------------------------------------ SR-318


@pytest.mark.sr("SR-318")
def test_sr318_ex1_scene_and_mp4_sit_beside_the_study(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    _rendered(accepted, tmp_path)
    assert (study.folder(accepted) / f"{SLUG}.md").is_file()
    for suffix in (".py", ".mp4", ".storyboard.json", ".vtt"):
        assert video.path(accepted, SLUG, CLIP, suffix).is_file()
    assert study.folder(accepted) not in video.frames_dir(accepted, SLUG, CLIP).parents   # not committed


@pytest.mark.sr("SR-318")
def test_sr318_ex2_a_clone_needs_no_render(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    _rendered(accepted, tmp_path)
    _study(accepted, "check", SLUG, "--clip", CLIP, "--pass", "--reviewer", "agent-2")
    shutil.rmtree(accepted / ".plumb" / "cache")     # a clone has the committed files only
    assert _state(accepted) == "ready"
    assert video.path(accepted, SLUG, CLIP, ".mp4").is_file() and len(popen) == 1


@pytest.mark.sr("SR-318")
def test_sr318_ex3_a_changed_scene_replaces_the_mp4(
        accepted: Path, tmp_path: Path, popen: list[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(video, "run_manim", lambda s, m: _fake_mp4(m / "a.mp4", 4))
    _rendered(accepted, tmp_path)
    first = video.path(accepted, SLUG, CLIP, ".mp4").read_bytes()
    _study(accepted, "check", SLUG, "--clip", CLIP, "--pass", "--reviewer", "agent-2")
    monkeypatch.setattr(video, "run_manim", lambda s, m: _fake_mp4(m / "b.mp4", 6))
    assert _study(accepted, "render", SLUG, "--clip", CLIP, "--scene", _file(tmp_path, "g.py", SCENE + "#\n")) == 0
    video.job(accepted, SLUG, CLIP)
    assert video.path(accepted, SLUG, CLIP, ".mp4").read_bytes() != first


# ------------------------------------------------------------------------ SR-364


@pytest.mark.sr("SR-364")
def test_sr364_ex1_the_storyboard_is_kept_before_any_scene(accepted: Path, tmp_path: Path) -> None:
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(_board()))) == 0
    kept = json.loads(video.path(accepted, SLUG, CLIP, ".storyboard.json").read_text(encoding="utf-8"))
    assert {"question", "goals", "context", "beats"} <= set(kept)
    assert not video.path(accepted, SLUG, CLIP, ".py").exists()


@pytest.mark.sr("SR-364")
def test_sr364_ex2_a_missing_part_starts_no_render_and_is_named(
        accepted: Path, tmp_path: Path, popen: list[Any], capsys: pytest.CaptureFixture) -> None:
    scene = _file(tmp_path, "f.py", SCENE)
    store = video.path(accepted, SLUG, CLIP, ".storyboard.json")
    assert _study(accepted, "render", SLUG, "--clip", CLIP, "--scene", scene) != 0      # no storyboard at all
    bad = _board()
    bad["beats"][1]["subtitle"] = ""
    for part, board in (("no goals", _board(goals=[])), ("no context", _board(context="")),
                        ("beat 2 has no subtitle", bad)):
        capsys.readouterr()
        store.write_text(json.dumps(board), encoding="utf-8")
        assert _study(accepted, "render", SLUG, "--clip", CLIP, "--scene", scene) != 0
        assert part in capsys.readouterr().err
    assert popen == [] and _state(accepted) == ""


@pytest.mark.sr("SR-364")
def test_sr364_ex3_the_last_beat_recaps_the_goals(
        accepted: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    board = _board()
    del board["beats"][-1]["recap"]
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(board))) != 0
    assert "recap" in capsys.readouterr().err
    assert not video.path(accepted, SLUG, CLIP, ".storyboard.json").exists()


@pytest.mark.sr("SR-364")
def test_sr364_ex4_eight_beats_over_two_minutes_are_kept(accepted: Path, tmp_path: Path) -> None:
    eight = _board(beats=[{"shows": "x", "subtitle": "Word.", "seconds": 15}] * 7
                   + [{"shows": "x", "subtitle": "Word.", "seconds": 15, "recap": True}])
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(eight))) == 0


@pytest.mark.sr("SR-364")
def test_sr364_ex5_a_subtitle_without_time_to_read_starts_no_render(
        accepted: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    board = _board()
    board["beats"][0].update(subtitle=" ".join(["word"] * 30), seconds=4)
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(board))) != 0
    assert "beat 1 needs at least 10 seconds" in capsys.readouterr().err


# ------------------------------------------------------------------------ SR-365


@pytest.mark.sr("SR-365")
def test_sr365_ex1_one_cue_per_beat_starting_with_its_beat(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    _rendered(accepted, tmp_path)
    text = video.path(accepted, SLUG, CLIP, ".vtt").read_text(encoding="utf-8")
    assert text.startswith("WEBVTT\n") and text.count(" --> ") == 3
    for span in ("00:00:00.000 --> 00:00:04.000", "00:00:04.000 --> 00:00:07.000",
                 "00:00:07.000 --> 00:00:11.000"):
        assert span in text


@pytest.mark.sr("SR-365")
def test_sr365_ex3_twelve_words_stay_at_least_four_seconds(
        accepted: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    board = _board()
    board["beats"][0]["subtitle"] = "one two three four five six seven eight nine ten eleven twelve"
    board["beats"][0]["seconds"] = 3
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(board))) != 0
    assert "at least 4 seconds" in capsys.readouterr().err
    board["beats"][0]["seconds"] = 4
    assert _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
                  _file(tmp_path, "sb.json", json.dumps(board))) == 0
    cue = video.cues(board)[0]
    assert cue["end"] - cue["start"] >= 4


# ------------------------------------------------------------------------ SR-366


@pytest.mark.sr("SR-366")
def test_sr366_ex1_a_pass_keeps_the_verdict_and_the_video_is_announced(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    _rendered(accepted, tmp_path)
    [line] = [x for x in study.accepted_lines(accepted) if "rendered" in x]
    assert "independent reviewer agent" in line and f"plumb study check {SLUG} --clip {CLIP}" in line
    assert _study(accepted, "check", SLUG, "--clip", CLIP, "--pass", "--reviewer", "agent-2") == 0
    kept = json.loads(video.path(accepted, SLUG, CLIP, ".check.json").read_text(encoding="utf-8"))
    assert kept["verdict"] == "pass" and kept["reviewer"] == "agent-2"
    assert not [x for x in study.accepted_lines(accepted) if "rendered" in x]


@pytest.mark.sr("SR-366")
def test_sr366_ex2_a_fail_shows_nothing_and_names_the_beat(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    _rendered(accepted, tmp_path)
    assert _study(accepted, "check", SLUG, "--clip", CLIP, "--fail", "--reviewer", "agent-2") != 0   # no reason
    assert _study(accepted, "check", SLUG, "--clip", CLIP, "--fail", "--reviewer", "agent-2",
                  "--reason", "beat 2 shows no judges") == 0
    assert _state(accepted) == "failed" and "beat 2" in _state(accepted, "reason")


@pytest.mark.sr("SR-366")
def test_sr366_ex3_the_reviewer_gets_storyboard_cues_and_frames(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None,
        capsys: pytest.CaptureFixture) -> None:
    _rendered(accepted, tmp_path)
    capsys.readouterr()
    assert _study(accepted, "frames", SLUG, "--clip", CLIP, "--json") == 0
    seen = json.loads(capsys.readouterr().out)
    assert seen["storyboard"]["goals"] and len(seen["cues"]) == 3
    assert [Path(p).name for p in seen["frames"]] == ["beat-1.png", "beat-2.png", "beat-3.png",
                                                      "last.png"]
    assert all(Path(p).is_file() for p in seen["frames"])
    assert _study(accepted, "check", SLUG, "--clip", CLIP, "--pass", "--reviewer", " ") != 0     # a named reviewer


@pytest.mark.sr("SR-366")
def test_sr366_ex4_a_failed_revision_is_final(
        accepted: Path, tmp_path: Path, popen: list[Any], fake: None,
        capsys: pytest.CaptureFixture) -> None:
    _rendered(accepted, tmp_path)
    _study(accepted, "check", SLUG, "--clip", CLIP, "--fail", "--reason", "beat 1 is blank", "--reviewer", "a2")
    assert _render(accepted, tmp_path) == 0          # the one revision
    assert _state(accepted, "revisions") == 1
    video.job(accepted, SLUG, CLIP)
    _study(accepted, "check", SLUG, "--clip", CLIP, "--fail", "--reason", "still blank", "--reviewer", "a3")
    capsys.readouterr()
    assert _study(accepted, "render", SLUG, "--clip", CLIP, "--scene", _file(tmp_path, "f.py", SCENE)) != 0
    assert "no further render" in capsys.readouterr().err
    assert len(popen) == 2 and _state(accepted) == "failed"


@pytest.mark.sr("SR-317")
def test_sr317_ex3_manimlib_scenes_are_refused(
        accepted: Path, tmp_path: Path, popen: list[Any], capsys: pytest.CaptureFixture) -> None:
    _study(accepted, "storyboard", SLUG, "--clip", CLIP, "--file",
           _file(tmp_path, "sb.json", json.dumps(_board())))
    capsys.readouterr()
    assert _study(accepted, "render", SLUG, "--clip", CLIP, "--scene",
                  _file(tmp_path, "m.py", "from manimlib import *\n")) != 0
    assert "manimlib" in capsys.readouterr().err
    assert popen == []


# ------------------------------------------------------------------------ SR-370


@pytest.mark.sr("SR-370")
def test_sr370_ex1_the_body_places_its_clips_in_order(repo: Path) -> None:
    body = ("Para one.\n\n```mermaid\nflowchart LR\n  a --> b\n```\n\n```video\none-record\n```"
            "\n\nPara two.\n")
    assert video.clips_in(study.get(_accept(repo, body), SLUG)["body"]) == ["one-record"]


@pytest.mark.sr("SR-370")
def test_sr370_ex2_two_clips_and_no_diagram_are_kept(repo: Path) -> None:
    _accept(repo, "A.\n\n```video\nfirst\n```\n\nB.\n\n```video\nsecond\n```\n")
    assert video.clips_in(study.get(repo, SLUG)["body"]) == ["first", "second"]


@pytest.mark.sr("SR-370")
def test_sr370_ex3_a_video_block_below_depth_video_is_refused(repo: Path) -> None:
    for depth in ("md", "diagrams"):
        slug = study.propose(repo, title=f"A {depth} mix", why="w", depth=depth, loop="l",
                             step="s", asked=True)
        study.choose(repo, slug, depth)
        with pytest.raises(ValueError, match="```video cascade"):
            study.add(repo, slug, "Text.\n\n```video\ncascade\n```\n")
        if depth == "md":
            with pytest.raises(ValueError, match="no diagram"):
                study.add(repo, slug, "```mermaid\nflowchart LR\n  a --> b\n```\n")


@pytest.mark.sr("SR-370")
def test_sr370_ex4_a_rendering_clip_and_an_unplaced_clip(
        accepted: Path, tmp_path: Path, popen: list[Any]) -> None:
    assert _render(accepted, tmp_path) == 0
    assert _state(accepted) == "rendering"
    with pytest.raises(ValueError, match="places no clip"):
        video.storyboard(accepted, SLUG, "elsewhere", json.dumps(_board()))


@pytest.mark.sr("SR-370")
def test_sr370_ex5_a_failed_clip_leaves_the_others(
        repo: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    accepted = _accept(repo, BODY + "\n```video\nsecond\n```\n")
    for clip, ok in ((CLIP, True), ("second", False)):
        video.storyboard(accepted, SLUG, clip, json.dumps(_board()))
        video.render(accepted, SLUG, clip, Path(_file(tmp_path, "f.py", SCENE)))
        video.job(accepted, SLUG, clip)
        video.check(accepted, SLUG, clip, ok, "" if ok else "beat 2 is blank", "agent-2")
    clips = study.get(accepted, SLUG)["clips"]
    assert clips[CLIP]["state"] == "ready"
    assert clips["second"] == {"state": "failed", "reason": "beat 2 is blank", "revisions": 0}


@pytest.mark.sr("SR-371")
def test_sr371_ex3_progress_lasts_through_renders_and_ends_with_the_last_passed_check(
        repo: Path, tmp_path: Path, popen: list[Any], fake: None) -> None:
    """SR-371 EX-3: `add` keeps the progress of a study with a clip; the last clip's pass ends it."""
    assert _study(repo, "propose", "--title", TITLE, "--why", "the owner asked",
                  "--depth", "video", "--asked") == 0
    study.choose(repo, SLUG, "video")
    assert _study(repo, "progress", SLUG, "--step", "body", "--done", "1", "--total", "4") == 0
    study.add(repo, SLUG, BODY)
    assert study.get(repo, SLUG)["progress"]["step"] == "body"
    assert _study(repo, "progress", SLUG, "--step", "render", "--done", "2", "--total", "4") == 0
    _rendered(repo, tmp_path)
    assert "progress" in study.get(repo, SLUG)
    assert _study(repo, "check", SLUG, "--clip", CLIP, "--pass", "--reviewer", "agent-2") == 0
    assert "progress" not in study.get(repo, SLUG)


@pytest.mark.sr("SR-371")
def test_sr371_ex3_finish_ends_the_progress(repo: Path) -> None:
    """SR-371 EX-3: `study progress --finish` ends the bar of a written study."""
    assert _study(repo, "propose", "--title", TITLE, "--why", "the owner asked",
                  "--depth", "video", "--asked") == 0
    study.choose(repo, SLUG, "video")
    assert _study(repo, "progress", SLUG, "--step", "body", "--done", "1", "--total", "4") == 0
    study.add(repo, SLUG, BODY)
    assert _study(repo, "progress", SLUG, "--finish") == 0
    assert "progress" not in study.get(repo, SLUG)
