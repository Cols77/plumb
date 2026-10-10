"""Progress of a long step (SHOW, SR-108): the file ``progress`` of a session, or of the shell
(``.plumb/session/cli/progress``), and what is drawn for the person waiting.

``Reporter`` writes the progress file at once on every update (the status line reads it) and,
when it is given a ``stream``, draws the same message there: one bar line redrawn in place when
the stream is a terminal, bounded plain lines at a steady interval otherwise. An execution that
ends within ``progress_min_s`` (two seconds) draws nothing; a failure is always drawn, as one
line that names the step; ``done(final)`` keeps an end line. With no ``stream`` nothing is drawn
(a background worker has no screen). ``status_text`` is what the status line shows."""

from __future__ import annotations

import os
import threading
import time
from calendar import timegm
from pathlib import Path
from typing import Any, TextIO

from plumb.contracts import Progress

MIN_S = 2.0              # understand.progress_min_s: nothing is drawn before this
INTERVAL_S = 1.0         # understand.progress_interval_s: a terminal bar redraws this often
PLAIN_INTERVAL_S = 5.0   # plain lines come this far apart
MAX_PLAIN_LINES = 40     # and never more than this many before the end line
BAR_WIDTH = 20
STALE_S = 5.0            # a running line not updated for this long, its process gone, is stale
END_LINE_S = 30.0        # an end line (a ``done`` file with words) is shown this long
FINISHED = "{step}: finished"
FAILED = "{step}: stopped"
FAILURES_FLAG = "the checks failed {n} times in a row"
LABELS = {"merge-check": "merge check"}
# one-call kinds have no count worth showing
COUNTLESS = frozenset({"read", "clarify"})


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def elapsed_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m{seconds % 60:02d}s"


def bar(done: int, total: int, width: int = BAR_WIDTH) -> str:
    fill = max(0, min(width, round(width * done / total))) if total > 0 else 0
    head = ">" if 0 < fill < width else ""
    return "=" * (fill - len(head)) + head + "." * (width - fill)


class Reporter:
    def __init__(self, root: Path, session: str | None = None, kind: str = "", *,
                 stream: TextIO | None = None, clock: Any = time.monotonic,
                 min_s: float = MIN_S, interval_s: float = INTERVAL_S,
                 plain_interval_s: float = PLAIN_INTERVAL_S,
                 max_lines: int = MAX_PLAIN_LINES, tty: bool | None = None) -> None:
        from plumb.understand import files

        self._files = files
        self.path = files.progress_path(Path(root), session)
        self.kind = kind
        self.started = _now()
        self.stream = stream
        self._clock = clock
        self._t0 = clock()
        self._min_s, self._interval_s = float(min_s), float(interval_s)
        self._plain_s, self._max_lines = float(plain_interval_s), int(max_lines)
        if tty is None:
            try:
                tty = bool(stream is not None and stream.isatty())
            except (AttributeError, ValueError, OSError):
                tty = False
        self._tty = tty
        self._step, self._done, self._total, self._item = "", 0, 0, ""
        self._last: float | None = None      # when the display last changed
        self._drawn = False                   # something was shown
        self._open = False                    # a terminal line is waiting for its newline
        self._lines = 0
        self._lock = threading.RLock()
        self._beat: threading.Event | None = None

    # ------------------------------------------------------------------ the file
    def _write(self, step: str, done: int, total: int, state: str) -> None:
        data = self._files.progress_to_json(Progress(
            step=step, done=done, total=total, started=self.started, updated=_now(),
            state=state, kind=self.kind))  # type: ignore[arg-type]
        data["pid"] = os.getpid()
        try:
            self._files.write_json_atomic(self.path, data)
        except OSError:
            pass                              # a courtesy: it never stops the work

    # ------------------------------------------------------------------ the display
    def _text(self) -> str:
        if self._total > 0:
            if self._tty:
                head = f"{self._step} [{bar(self._done, self._total)}] {self._done}/{self._total}"
            else:
                head = f"{self._step}: {self._done} of {self._total}"
            return f"{head} {self._item}".rstrip() if self._item else head
        return f"{self._step}, {elapsed_text(self._clock() - self._t0)} so far"

    def _emit(self, text: str, *, final: bool = False) -> None:
        stream = self.stream
        if stream is None:
            return
        try:
            if self._tty:
                stream.write("\r" + text + "\x1b[K" + ("\n" if final else ""))
                self._open = not final
            else:
                stream.write(text + "\n")
            stream.flush()
        except (OSError, ValueError):
            self.stream = None
            return
        self._drawn = True

    def _draw(self) -> None:
        if self.stream is None:
            return
        now = self._clock()
        if now - self._t0 < self._min_s:
            return
        gap = self._interval_s if self._tty else self._plain_s
        if self._last is not None and now - self._last < gap:
            return
        if not self._tty and self._lines >= self._max_lines:
            return
        self._last = now
        self._lines += 0 if self._tty else 1
        self._emit(self._text())

    # ------------------------------------------------------------------ the calls
    def update(self, step: str, done: int = 0, total: int = 0, *,
               state: str = "running", item: str = "") -> None:
        with self._lock:
            self._step, self._done, self._total, self._item = step, done, total, item
            self._write(step, done, total, state)
            if state == "running":
                self._draw()

    def tick(self) -> None:
        """Say again what is going on, so the file and the display stay fresh while one
        step takes long (the elapsed time moves)."""
        with self._lock:
            if self._step:
                self._write(self._step, self._done, self._total, "running")
                self._draw()

    def done(self, final: str = "") -> None:
        """End the execution; a non-empty ``final`` is an end line the status line shows. It is
        also the last thing drawn, but only when something was drawn before."""
        with self._lock:
            self.stop_beat()
            self._write(final, 0, 0, "done")
            if self._drawn:
                self._emit(final or FINISHED.format(step=self._step), final=True)

    def failed(self, step: str = "") -> None:
        """The execution stopped midway: one line names the step that failed (drawn at any
        time), and the progress file no longer says it runs."""
        with self._lock:
            self.stop_beat()
            self._write(step, self._done, self._total, "failed")
            self._emit(step or FAILED.format(step=self._step), final=True)

    # ------------------------------------------------------------------ the beat
    def start_beat(self) -> None:
        """Tick every interval from a thread, for a step that cannot call ``update``."""
        with self._lock:
            if self._beat is not None:
                return
            stop = self._beat = threading.Event()

        def run() -> None:
            while not stop.wait(self._interval_s):
                self.tick()

        threading.Thread(target=run, daemon=True).start()

    def stop_beat(self) -> None:
        beat, self._beat = self._beat, None
        if beat is not None:
            beat.set()

    def __enter__(self) -> Reporter:
        self.start_beat()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop_beat()


# ---------------------------------------------------------------------- reading it back


def _age(updated: str, now: float) -> float:
    try:
        return now - timegm(time.strptime(updated, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return 0.0


def _alive(pid: Any) -> bool:
    """Whether a process with this id is still running. Never signals it: on Windows
    ``os.kill`` would terminate the process, so it is asked politely there."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                        and code.value == 259)               # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, SystemError):
        return False
    return True


def progress_text(found: Progress) -> str:
    """The words the status line shows for a running execution: ``[label: ]step[ · done/total]``."""
    label = LABELS.get(found.kind)
    text = f"{label}: {found.step}" if label else found.step
    if found.total > 0 and found.kind not in COUNTLESS:
        text += f" · {found.done}/{found.total}"
    return text


def shown(root: Path, who: str | None, now: float | None = None) -> str:
    """What the progress file of ``who`` (a session, or None for the shell's) says now: the
    running step; or an end line for ``END_LINE_S`` seconds after it was written; nothing for a
    failed or stale one (not updated for ``STALE_S`` seconds with its process gone)."""
    from plumb.understand import files

    path = files.progress_path(Path(root), who)
    raw = files.read_json(path)
    found = files.progress_from_json(raw)
    if found is None or not found.step:
        return ""
    when = time.time() if now is None else now
    age = _age(found.updated, when)
    if found.state == "done":
        return found.step if age <= END_LINE_S else ""
    if found.state != "running":
        return ""
    pid = raw.get("pid") if isinstance(raw, dict) else None
    if age > STALE_S and not _alive(pid):
        return ""
    return progress_text(found)


def status_text(root: Path, session: str | None) -> str:
    """The progress text of the running execution (the session's, else the shell's), or an
    empty string."""
    from plumb.understand import files

    for who in (session, files.CLI_SESSION):
        if who is None:
            continue
        text = shown(Path(root), who)
        if text:
            return text
    return ""


def failure_flag(root: Path, session: str | None, limit: int = 3) -> str:
    """``the checks failed 3 times in a row`` once ``queue.consecutive_failures`` reaches
    ``limit`` (spec 9.1); nothing otherwise. Reads no file unless the counter exists."""
    from plumb.understand import files

    if not session or not files.failures_path(Path(root), session).exists():
        return ""
    from plumb.understand import queue

    count = queue.consecutive_failures(Path(root), session)
    return FAILURES_FLAG.format(n=count) if count >= limit else ""
