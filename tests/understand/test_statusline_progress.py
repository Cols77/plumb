"""SHOW P2: the status line shows the live progress of the session and of the shell
(SR-108 EX-3, EX-6, EX-7; SR-107 / spec 8 end line; spec 9.1 three failures)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from understand.fakes import owner_level

from plumb.hosts.claude_code import snapshot, statusline
from plumb.present import owner_text
from plumb.understand import files

pytestmark = pytest.mark.sr("SR-272")

SESSION = "s1"


def _stamp(ago: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago))


def _progress(root: Path, session: str | None, *, step: str, kind: str, done: int = 0,
              total: int = 0, state: str = "running", ago: float = 0.0,
              pid: int | None = None) -> None:
    files.write_json_atomic(files.progress_path(root, session), {
        "step": step, "done": done, "total": total, "started": _stamp(ago + 5),
        "updated": _stamp(ago), "state": state, "kind": kind,
        "pid": os.getpid() if pid is None else pid})


def _line(repo: Path, session: str | None = SESSION) -> str:
    snapshot.write_snapshot(repo, _snap())
    out = io.StringIO()
    stdin = io.StringIO(json.dumps({"session_id": session} if session else {}))
    assert statusline.main(root=repo, stdin=stdin, stdout=out) == 0
    return out.getvalue().strip()


def _snap():
    from plumb.contracts import StatusSnapshot

    return StatusSnapshot(at="2026-10-06T04:00:00Z", requirements_total=14,
                          requirements_confirmed=12, proposed=2, stale_links=1,
                          dangling_links=0, tests="ok")


def _dead_pid() -> int:
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True)
    return int(done.stdout)


def test_sr108_ex3_merge_check_line(repo: Path) -> None:
    _progress(repo, None, step="running the full suite", kind="merge-check", done=120,
              total=400)
    assert _line(repo) == "plumb ⏳ merge check: running the full suite · 120/400"


def test_sr108_ex6_backlog_line(repo: Path) -> None:
    _progress(repo, SESSION, step="judging the backlog", kind="judge", done=10, total=160)
    line = _line(repo)
    assert line.startswith("plumb ● awaits you")          # the card stays
    assert line.endswith("judging the backlog · 10/160")
    assert owner_level("judging the backlog · 10/160") == []


def test_a_one_call_step_shows_no_count(repo: Path) -> None:
    _progress(repo, SESSION, step="reading your answer", kind="read", done=1, total=2)
    assert _line(repo).endswith("| reading your answer")


def test_stale_progress_not_shown(repo: Path) -> None:
    gone = _dead_pid()
    _progress(repo, None, step="running the full suite", kind="merge-check", done=1, total=4,
              ago=20, pid=gone)
    _progress(repo, SESSION, step="judging the backlog", kind="judge", done=3, total=9,
              ago=20, pid=gone)
    line = _line(repo)
    assert "⏳" not in line and "judging" not in line
    # not updated for a while, but its process is still there: still running
    _progress(repo, SESSION, step="judging the backlog", kind="judge", done=3, total=9,
              ago=20, pid=os.getpid())
    assert _line(repo).endswith("judging the backlog · 3/9")
    # a file with no process named is as good as gone once it is old
    files.write_json_atomic(files.progress_path(repo, SESSION), {
        "step": "judging the backlog", "done": 3, "total": 9, "started": _stamp(30),
        "updated": _stamp(20), "state": "running", "kind": "judge"})
    assert "judging" not in _line(repo)


def test_failed_line_stops_showing_running(repo: Path) -> None:
    _progress(repo, None, step="running the full suite stopped at 50 of 400", kind="merge-check",
              done=50, total=400, state="failed")
    assert "⏳" not in _line(repo) and "stopped" not in _line(repo)


def test_three_failures_flag(repo: Path, engine_standins) -> None:
    def failures(n: int) -> None:
        files.write_json_atomic(files.failures_path(repo, SESSION), {
            "v": 1, "consecutive": n,
            "last": {"job": "read-0", "kind": "read", "step": "run", "at": _stamp()}})

    failures(2)
    assert "in a row" not in _line(repo)
    failures(3)
    line = _line(repo)
    assert line.endswith("the checks failed 3 times in a row")
    assert owner_level("the checks failed 3 times in a row") == []
    failures(0)
    assert "in a row" not in _line(repo)
    # the snapshot carries the flag too, for a line that does not know the session
    path = snapshot.write_snapshot(repo, _snap(), failures=3)
    assert json.loads(path.read_text(encoding="utf-8"))["understand_failures"] == 3
    out = io.StringIO()
    statusline.main(root=repo, stdin=io.StringIO(""), stdout=out)
    assert out.getvalue().strip().endswith("the checks failed 3 times in a row")


def test_end_line_shown_then_gone(repo: Path) -> None:
    end = owner_text.BACKLOG_DONE.format(judged=160, cards=4)
    _progress(repo, SESSION, step=end, kind="judge", state="done", ago=2)
    assert _line(repo).endswith(end)
    _progress(repo, SESSION, step=end, kind="judge", state="done", ago=40)
    assert end not in _line(repo)
    _progress(repo, SESSION, step="", kind="judge", state="done", ago=1)    # done, no words
    assert _line(repo).count("|") == 0


def test_ascii_line_when_the_card_is_ascii(repo: Path) -> None:
    _progress(repo, None, step="running the full suite", kind="merge-check", done=120, total=400)
    snapshot.write_snapshot(repo, _snap(), present=type("P", (), {"ascii": True, "card": "x"})())
    out = io.StringIO()
    statusline.main(root=repo, stdin=io.StringIO(""), stdout=out)
    line = out.getvalue().strip()
    assert line.isascii() and "merge check: running the full suite" in line


def test_a_stream_that_cannot_print_the_glyph_falls_back(repo: Path) -> None:
    _progress(repo, None, step="running the full suite", kind="merge-check", done=120, total=400)

    class Narrow(io.StringIO):
        def write(self, text: str) -> int:
            text.encode("ascii")                 # raises UnicodeEncodeError
            return super().write(text)

    out = Narrow()
    snapshot.write_snapshot(repo, _snap())
    statusline.main(root=repo, stdin=io.StringIO(""), stdout=out)
    assert "merge check: running the full suite" in out.getvalue()


def test_the_status_line_never_signals_the_process_it_checks() -> None:
    from plumb.progress import _alive

    assert _alive(os.getpid()) is True               # and we are still here to say so
    assert _alive(_dead_pid()) is False
    assert _alive(None) is False and _alive(-3) is False
