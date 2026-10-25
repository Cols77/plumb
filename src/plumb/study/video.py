"""Video studies (SR-316, SR-318, SR-364, SR-365, SR-366; INT-093, INT-111): the storyboard that
comes first, the Manim render in the background, the subtitle track from the beats, the frames
for an independent reviewer and the reviewer's verdict. The files of study ``<slug>`` sit in
``.plumb/studies/``: ``.storyboard.json``, ``.py``, ``.mp4``, ``.vtt``, ``.check.json``; the
frames go to ``.plumb/cache/studies/<slug>/`` (not committed)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from plumb import study

MAX_SECONDS = 90
BEATS = (3, 6)


def path(root: Path, slug: str, suffix: str) -> Path:
    return study.folder(root) / f"{slug}{suffix}"


def frames_dir(root: Path, slug: str) -> Path:
    return Path(root) / ".plumb" / "cache" / "studies" / slug


def _words(text: Any) -> int:
    return len(str(text).split())


def problems(sb: Any) -> list[str]:
    """What a storyboard lacks (SR-364 EX-2, EX-4); empty when it can be rendered."""
    if not isinstance(sb, dict):
        return ["the storyboard is a JSON object"]
    out = [f"the storyboard has no {k}" for k in ("question", "goals", "context")
           if not sb.get(k)]
    beats = [b for b in sb.get("beats") or () if isinstance(b, dict)]
    if not BEATS[0] <= len(beats) <= BEATS[1] or len(beats) != len(sb.get("beats") or ()):
        out.append(f"the video must fit in {BEATS[0]} to {BEATS[1]} beats and {MAX_SECONDS} "
                   f"seconds (the storyboard has {len(sb.get('beats') or ())} beats)")
    for n, b in enumerate(beats, 1):
        if not str(b.get("subtitle") or "").strip():
            out.append(f"beat {n} has no subtitle")
        elif not str(b.get("shows") or "").strip():
            out.append(f"beat {n} says nothing of what it shows")
        try:
            need = max(1.5, _words(b.get("subtitle", "")) / 3)
            if float(b.get("seconds")) < need:
                out.append(f"beat {n} needs at least {need:g} seconds for its subtitle")
        except (TypeError, ValueError):
            out.append(f"beat {n} has no seconds")
    try:
        if sum(float(b.get("seconds")) for b in beats) > MAX_SECONDS:
            out.append(f"the video must fit in {BEATS[0]} to {BEATS[1]} beats and "
                       f"{MAX_SECONDS} seconds (the beats add up to more)")
    except (TypeError, ValueError):
        pass
    if beats and beats[-1].get("recap") is not True:
        out.append("the last beat must recap the goals (recap: true) and point to the text")
    return out


def storyboard(root: Path, slug: str, raw: str) -> None:
    """Keep a valid storyboard beside the study (SR-364 EX-1); a refusal names what is missing."""
    study.get(root, slug)
    try:
        sb = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"the storyboard is not JSON: {exc}") from exc
    if found := problems(sb):
        raise ValueError("; ".join(found))
    study._write(path(root, slug, ".storyboard.json"),
                 json.dumps(sb, indent=2, ensure_ascii=False) + "\n")


def _load(root: Path, slug: str) -> dict[str, Any]:
    file = path(root, slug, ".storyboard.json")
    if not file.is_file():
        raise ValueError("no storyboard yet: plumb study storyboard first (SR-364)")
    sb = json.loads(file.read_text(encoding="utf-8"))
    if found := problems(sb):
        raise ValueError("; ".join(found))
    return sb


def _set(root: Path, slug: str, video: str, reason: str = "", revisions: int | None = None) -> None:
    found = study.get(root, slug)
    fields = {**study._fields(found), "video": video, "video_reason": reason,
              "revisions": found.get("revisions") or 0 if revisions is None else revisions,
              "status": found["status"]}
    fields["revisions"] = int(fields["revisions"])
    study._write(study.folder(root) / f"{slug}.md", study._front(fields) + found["body"])


def render(root: Path, slug: str, scene: Path) -> None:
    """Start the background render (SR-316 EX-1) and return at once."""
    found = study.get(root, slug)
    if found.get("depth") != "video":
        raise ValueError(f"the study {found['title']} was not chosen at depth video: no render")
    _load(root, slug)
    source = Path(scene).read_text(encoding="utf-8")
    if re.search(r"^\s*(from|import)\s+manimlib\b", source, re.M):
        raise ValueError("the scene imports manimlib: use Manim Community Edition "
                         "(from manim import *)")
    state, revisions = found.get("video", ""), int(found.get("revisions") or 0)
    if state == "rendering":
        raise ValueError("a render of this study is already running")
    if state == "failed":
        if revisions:
            raise ValueError("the video failed after its one revision: no further render "
                             f"({found.get('video_reason', '')})")
        revisions = 1
    study._write(path(root, slug, ".py"), source)
    path(root, slug, ".check.json").unlink(missing_ok=True)
    _set(root, slug, "rendering", "", revisions)
    from plumb.background import popen_options

    subprocess.Popen([sys.executable, "-m", "plumb", "study", "render-job", slug,
                      "--root", str(root)], **popen_options(root))


def run_manim(scene: Path, media: Path) -> Path:
    """Render the scene with Manim Community (no LaTeX, no OpenGL); the mp4 it made."""
    done = subprocess.run([sys.executable, "-m", "manim", "-ql", "--disable_caching",
                           "--media_dir", str(media), str(scene)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          # Manim imports the scene from .plumb/studies/: no __pycache__ there
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    mp4 = [p for p in media.rglob("*.mp4") if "partial_movie_files" not in p.parts]
    if done.returncode or not mp4:
        lines = [x.strip() for x in (done.stderr + done.stdout).splitlines() if x.strip()]
        raise RuntimeError(lines[-1] if lines else "manim made no video")
    return max(mp4, key=lambda p: p.stat().st_mtime_ns)


def _stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def cues(sb: dict[str, Any]) -> list[dict[str, Any]]:
    """One cue per beat, from the beats' cumulative seconds (SR-365 EX-1)."""
    out, at = [], 0.0
    for b in sb["beats"]:
        out.append({"start": at, "end": at + float(b["seconds"]), "text": b["subtitle"].strip()})
        at += float(b["seconds"])
    return out


def vtt(sb: dict[str, Any]) -> str:
    return "WEBVTT\n\n" + "".join(
        f"{n}\n{_stamp(c['start'])} --> {_stamp(c['end'])}\n{c['text']}\n\n"
        for n, c in enumerate(cues(sb), 1))


def extract_frames(mp4: Path, sb: dict[str, Any], out: Path) -> list[Path]:
    """A PNG at each beat's midpoint and the last frame (SR-366); a beat past the video's end
    gets the last frame."""
    import av

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    wanted = [(c["start"] + c["end"]) / 2 for c in cues(sb)]
    saved: list[Path] = []
    last = None
    with av.open(str(mp4)) as container:
        for frame in container.decode(video=0):
            last = frame
            if len(saved) < len(wanted) and frame.time >= wanted[len(saved)]:
                saved.append(out / f"beat-{len(saved) + 1}.png")
                frame.to_image().save(saved[-1])
    if last is None:
        raise RuntimeError("the video has no frames")
    while len(saved) < len(wanted):
        saved.append(out / f"beat-{len(saved) + 1}.png")
        last.to_image().save(saved[-1])
    saved.append(out / "last.png")
    last.to_image().save(saved[-1])
    return saved


def job(root: Path, slug: str) -> None:
    """The background render: ``checking`` when it made the video, ``failed`` with the scene's
    last error line when it did not; nothing retries (SR-316 EX-3)."""
    try:
        sb = _load(root, slug)
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = run_manim(path(root, slug, ".py"), Path(tmp))
            shutil.move(mp4, path(root, slug, ".mp4"))    # replaces an older one (SR-318 EX-3)
        study._write(path(root, slug, ".vtt"), vtt(sb))
        extract_frames(path(root, slug, ".mp4"), sb, frames_dir(root, slug))
    except Exception as exc:    # the study keeps its text and says why
        _set(root, slug, "failed", f"the video could not be rendered: {exc}")
        return
    _set(root, slug, "checking")


def frames(root: Path, slug: str) -> dict[str, Any]:
    """What the independent reviewer sees (SR-366 EX-3): storyboard, subtitle cues, frames."""
    sb = _load(root, slug)
    shots = sorted(frames_dir(root, slug).glob("*.png"))
    if not shots:
        raise LookupError(f"no frames for {slug}: the render has not ended")
    return {"storyboard": sb, "cues": cues(sb), "frames": [str(p) for p in shots]}


def check(root: Path, slug: str, ok: bool, reason: str, reviewer: str) -> None:
    """The reviewer's verdict, kept beside the study (SR-366 EX-1, EX-2, EX-4)."""
    found = study.get(root, slug)
    if found.get("video") != "checking":
        raise ValueError(f"the video of {found['title']} is not waiting for a check")
    if not reviewer.strip() or (not ok and not reason.strip()):
        raise ValueError("a check names its reviewer, and a fail gives the reason (the beat "
                         "that failed and why)")
    study._write(path(root, slug, ".check.json"), json.dumps(
        {"verdict": "pass" if ok else "fail", "reason": reason.strip(),
         "reviewer": reviewer.strip()}, indent=2, ensure_ascii=False) + "\n")
    _set(root, slug, "ready" if ok else "failed", "" if ok else reason.strip())
