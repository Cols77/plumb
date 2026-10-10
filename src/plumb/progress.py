"""Progress of a long step (SHOW): the file ``progress`` of a session, or of the shell
(``.plumb/session/cli/progress``). Phase C skeleton: ``Reporter`` writes its file only (no
rendering, no throttle) and ``status_text`` returns the plain step text."""

from __future__ import annotations

import time
from pathlib import Path

from plumb.contracts import Progress


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Reporter:
    def __init__(self, root: Path, session: str | None = None, kind: str = "") -> None:
        from plumb.understand import files

        self._files = files
        self.path = files.progress_path(Path(root), session)
        self.kind = kind
        self.started = _now()

    def update(self, step: str, done: int = 0, total: int = 0, *,
               state: str = "running") -> None:
        self._files.write_json_atomic(self.path, self._files.progress_to_json(Progress(
            step=step, done=done, total=total, started=self.started, updated=_now(),
            state=state, kind=self.kind)))  # type: ignore[arg-type]

    def done(self) -> None:
        self.update("", state="done")

    def failed(self, step: str = "") -> None:
        self.update(step, state="failed")


def status_text(root: Path, session: str | None) -> str:
    """The plain step text of the running execution (the session's, else the shell's), or
    an empty string."""
    from plumb.understand import files

    for who in (session, files.CLI_SESSION):
        if who is None:
            continue
        found = files.progress_from_json(files.read_json(files.progress_path(Path(root), who)))
        if found is not None and found.state == "running" and found.step:
            return found.step
    return ""
