"""The study room's operations (SR-380: no card is drawn or pressed here any more)."""

import threading
from pathlib import Path

from iaso import study
from iaso.mod.session import refuse_under_marker


class BrowserService:
    def __init__(self, root: Path):
        refuse_under_marker("browser startup")
        self.root = Path(root).resolve()
        self.lock = threading.RLock()

    def workspace(self):
        return {"project": {"name": self.root.name, "root": str(self.root)}}

    # Studies and the understanding picture (DEC-151): the room's one section. Its
    # buttons correct the picture only; nothing reaches a session as an answer (DEC-152).
    def studies(self):
        with self.lock:
            return {
                "studies": [
                    self._video({k: v for k, v in s.items() if k != "body"})
                    for s in study.studies(self.root)
                    if s["status"] in study.WRITTEN    # an idea has no page (DEC-207)
                ],
                "understanding": self._understanding(),
            }

    def _understanding(self):
        return {"text": study.picture_text(self.root), **study.picture(self.root)}

    def open_study(self, slug):
        """The owner reads a study: it is opened, and the band's study line goes (SR-294)."""
        with self.lock:
            return self._video(study.mark(self.root, slug, "opened"))

    @staticmethod
    def _video(s):
        """Every study carries its clips' states (SR-319, SR-370): {} when it has none."""
        clips = s.get("clips")
        return {**s, "clips": clips if isinstance(clips, dict) else {}}

    def study_media(self, slug, clip, kind):
        """The bytes and type of a ready clip's mp4 or vtt (SR-319, SR-365); the path is built
        from the validated slug and clip name alone, never from a field of the study."""
        with self.lock:
            held = self._video(study.get(self.root, slug))["clips"].get(clip)
            if not isinstance(held, dict) or held.get("state") != "ready":
                raise LookupError("No video for this study")
            name, mime = (f"{slug}.{clip}.mp4", "video/mp4") if kind == "video" else (
                f"{slug}.{clip}.vtt", "text/vtt; charset=utf-8")
            path = study.folder(self.root) / name
            if not path.is_file():
                raise LookupError("No video for this study")
            return path.read_bytes(), mime

    def mark_study(self, slug, payload):
        how = payload.get("mark")
        if how not in ("known", "deeper"):
            raise ValueError("mark must be known or deeper")
        with self.lock:
            marked = study.mark(self.root, slug, how)
            return {"study": self._video(marked), "understanding": self._understanding()}

    def save_understanding(self, payload):
        with self.lock:
            study.save_picture(self.root, payload.get("text"))
            return self._understanding()
