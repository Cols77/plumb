"""Video clips of a study (SR-316, SR-318, SR-364, SR-365, SR-366, SR-370; INT-093, INT-111):
the storyboard that comes first, the Manim render in the background, the subtitle track from the
beats, the frames for an independent reviewer and the reviewer's verdict. A clip is a fenced
```video block in the study's body naming it; its state sits in the study's ``clips`` field and
its files in ``.plumb/studies/``: ``<slug>.<clip>.storyboard.json``, ``.py``, ``.mp4``,
``.vtt``, ``.check.json``; the frames go to ``.plumb/cache/studies/<slug>/<clip>/`` (not
committed)."""

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

CLIP = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_FENCE = re.compile(r"^```video[ \t]*\n(.*?)\n```", re.M | re.S)


def clips_in(body: str) -> list[str]:
    """The clip names a study's body places, in order (SR-370)."""
    return [m.group(1).strip() for m in _FENCE.finditer(body)]


def path(root: Path, slug: str, clip: str, suffix: str) -> Path:
    return study.folder(root) / f"{slug}.{clip}{suffix}"


def frames_dir(root: Path, slug: str, clip: str) -> Path:
    return Path(root) / ".plumb" / "cache" / "studies" / slug / clip


def _words(text: Any) -> int:
    return len(str(text).split())


def problems(sb: Any) -> list[str]:
    """What a storyboard lacks (SR-364 EX-2, EX-4); empty when it can be rendered."""
    if not isinstance(sb, dict):
        return ["the storyboard is a JSON object"]
    out = [f"the storyboard has no {k}" for k in ("question", "goals", "context")
           if not sb.get(k)]
    beats = [b for b in sb.get("beats") or () if isinstance(b, dict)]
    # the agent decides how many beats and how long (DEC-366); each beat is an object
    if not beats or len(beats) != len(sb.get("beats") or ()):
        out.append("the storyboard needs its beats, each an object")
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
    if beats and beats[-1].get("recap") is not True:
        out.append("the last beat must recap the goals (recap: true) and point to the text")
    return out


def _clip(found: dict[str, Any], clip: str) -> dict[str, Any]:
    """The clip's state; a clip the body does not place is refused (SR-370)."""
    if clip not in clips_in(found["body"]):
        raise ValueError(f"the study {found['title']} places no clip {clip!r}: write it in the "
                         "body as a ```video block first")
    held = (found.get("clips") or {}).get(clip) or {}
    return {"state": "", "reason": "", "revisions": 0, **held}


def storyboard(root: Path, slug: str, clip: str, raw: str) -> None:
    """Keep a valid storyboard beside the study (SR-364 EX-1); a refusal names what is missing."""
    _clip(study.get(root, slug), clip)
    try:
        sb = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"the storyboard is not JSON: {exc}") from exc
    if found := problems(sb):
        raise ValueError("; ".join(found))
    study._write(path(root, slug, clip, ".storyboard.json"),
                 json.dumps(sb, indent=2, ensure_ascii=False) + "\n")


def _load(root: Path, slug: str, clip: str) -> dict[str, Any]:
    file = path(root, slug, clip, ".storyboard.json")
    if not file.is_file():
        raise ValueError("no storyboard yet: plumb study storyboard first (SR-364)")
    sb = json.loads(file.read_text(encoding="utf-8"))
    if found := problems(sb):
        raise ValueError("; ".join(found))
    return sb


def _set(root: Path, slug: str, clip: str, state: str, reason: str = "",
         revisions: int | None = None) -> None:
    found = study.get(root, slug)
    held = _clip(found, clip)
    clips = {**(found.get("clips") or {}), clip: {
        "state": state, "reason": reason,
        "revisions": int(held["revisions"] if revisions is None else revisions)}}
    study._write(study.folder(root) / f"{slug}.md", study._front(
        {**study._fields(found), "clips": clips, "status": found["status"]}) + found["body"])


def render(root: Path, slug: str, clip: str, scene: Path) -> None:
    """Start the clip's background render (SR-316 EX-1) and return at once."""
    found = study.get(root, slug)
    if found.get("depth") != "video":
        raise ValueError(f"the study {found['title']} was not chosen at depth video: no render")
    held = _clip(found, clip)
    _load(root, slug, clip)
    source = Path(scene).read_text(encoding="utf-8")
    if re.search(r"^\s*(from|import)\s+manimlib\b", source, re.M):
        raise ValueError("the scene imports manimlib: use Manim Community Edition "
                         "(from manim import *)")
    state, revisions = held["state"], int(held["revisions"])
    if state == "rendering":
        raise ValueError(f"a render of the clip {clip} is already running")
    if state == "failed":
        if revisions:
            raise ValueError(f"the clip {clip} failed after its one revision: no further render "
                             f"({held['reason']})")
        revisions = 1
    study._write(path(root, slug, clip, ".py"), source)
    path(root, slug, clip, ".check.json").unlink(missing_ok=True)
    _set(root, slug, clip, "rendering", "", revisions)
    from plumb.background import popen_options

    subprocess.Popen([sys.executable, "-m", "plumb", "study", "render-job", slug,
                      "--clip", clip, "--root", str(root)], **popen_options(root))


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


def job(root: Path, slug: str, clip: str) -> None:
    """The background render: ``checking`` when it made the clip, ``failed`` with the scene's
    last error line when it did not; nothing retries (SR-316 EX-3)."""
    try:
        sb = _load(root, slug, clip)
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = run_manim(path(root, slug, clip, ".py"), Path(tmp))
            shutil.move(mp4, path(root, slug, clip, ".mp4"))   # replaces an older one (SR-318 EX-3)
        study._write(path(root, slug, clip, ".vtt"), vtt(sb))
        extract_frames(path(root, slug, clip, ".mp4"), sb, frames_dir(root, slug, clip))
    except Exception as exc:    # the rest of the study stays and the clip's place says why
        _set(root, slug, clip, "failed", f"the video could not be rendered: {exc}")
        return
    _set(root, slug, clip, "checking")


def frames(root: Path, slug: str, clip: str) -> dict[str, Any]:
    """What the independent reviewer sees (SR-366 EX-3): storyboard, subtitle cues, frames."""
    sb = _load(root, slug, clip)
    shots = sorted(frames_dir(root, slug, clip).glob("*.png"))
    if not shots:
        raise LookupError(f"no frames for {slug} {clip}: the render has not ended")
    return {"storyboard": sb, "cues": cues(sb), "frames": [str(p) for p in shots]}


def check(root: Path, slug: str, clip: str, ok: bool, reason: str, reviewer: str) -> None:
    """The reviewer's verdict, kept beside the study (SR-366 EX-1, EX-2, EX-4)."""
    found = study.get(root, slug)
    if _clip(found, clip)["state"] != "checking":
        raise ValueError(f"the clip {clip} of {found['title']} is not waiting for a check")
    if not reviewer.strip() or (not ok and not reason.strip()):
        raise ValueError("a check names its reviewer, and a fail gives the reason (the beat "
                         "that failed and why)")
    study._write(path(root, slug, clip, ".check.json"), json.dumps(
        {"verdict": "pass" if ok else "fail", "reason": reason.strip(),
         "reviewer": reviewer.strip()}, indent=2, ensure_ascii=False) + "\n")
    _set(root, slug, clip, "ready" if ok else "failed", "" if ok else reason.strip())
    after = study.get(root, slug)
    if ok and "progress" in after and not any(
            (c := _clip(after, name))["state"] not in ("ready", "failed")
            or (c["state"] == "failed" and not c["revisions"]) for name in clips_in(after["body"])):
        study.progress(root, slug, finish=True)    # the last clip is settled: the bar goes
