"""SHOW P1: the renderers of a long execution's progress (SR-108)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from plumb.progress import Reporter, status_text
from plumb.understand import files
from understand.fakes import owner_level

pytestmark = pytest.mark.sr("SR-272")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class Pipe(io.StringIO):
    def isatty(self) -> bool:
        return False


def _file(root: Path, session: str | None = None) -> dict:
    return json.loads(files.progress_path(root, session).read_text(encoding="utf-8"))


def test_sr108_ex1_terminal_bar_in_place_with_running_the_full_suite_120_of_400(
        tmp_path: Path) -> None:
    clock, out = Clock(), Terminal()
    reporter = Reporter(tmp_path, None, "full-run", stream=out, clock=clock)
    clock.advance(3)
    reporter.update("running the full suite", 120, 400, item="tests/verify/test_runner.py")
    text = out.getvalue()
    assert text.startswith("\r") and "\n" not in text       # one line, redrawn in place
    assert "running the full suite" in text and "120/400" in text
    assert "tests/verify/test_runner.py" in text
    assert "[" in text and "]" in text                      # the bar
    clock.advance(1)
    reporter.update("running the full suite", 121, 400, item="tests/verify/test_runner.py")
    assert out.getvalue().count("\r") == 2 and "\n" not in out.getvalue()
    reporter.done("full suite: 400 passed")
    assert out.getvalue().endswith("full suite: 400 passed\x1b[K\n")
    assert owner_level(text) == []


def test_ex2_plain_lines_steady_never_per_test_last_line_says_finished(tmp_path: Path) -> None:
    clock, out = Clock(), Pipe()
    reporter = Reporter(tmp_path, None, "full-run", stream=out, clock=clock)
    for n in range(1, 401):                                  # a test every 0.1 s: 40 s
        clock.advance(0.1)
        reporter.update("running the full suite", n, 400, item=f"tests/test_{n}.py")
    reporter.done("full suite finished: 400 passed")
    lines = out.getvalue().splitlines()
    assert "\r" not in out.getvalue() and "\x1b" not in out.getvalue()
    assert 3 <= len(lines) <= 12                             # steady, far fewer than 400
    assert lines[-1] == "full suite finished: 400 passed"
    assert "running the full suite" in lines[0]


def test_ex4_unknown_total_elapsed_no_percentage(tmp_path: Path) -> None:
    clock, out = Clock(), Terminal()
    reporter = Reporter(tmp_path, None, "map", stream=out, clock=clock)
    clock.advance(7)
    reporter.update("building the test map")
    text = out.getvalue().replace("[K", "")
    assert "building the test map" in text and "7s" in text
    assert "%" not in text and "[" not in text and "/" not in text


def test_ex5_under_two_seconds_nothing_shown(tmp_path: Path) -> None:
    clock, out = Clock(), Terminal()
    reporter = Reporter(tmp_path, None, "map", stream=out, clock=clock)
    for n in range(1, 9):
        clock.advance(0.2)
        reporter.update("checking", n, 8)
    reporter.done("all checked")
    assert out.getvalue() == ""


def test_ex7_failure_replaces_line_and_stops_running(tmp_path: Path) -> None:
    clock, out = Clock(), Pipe()
    reporter = Reporter(tmp_path, None, "full-run", stream=out, clock=clock)
    clock.advance(3)
    reporter.update("running the full suite", 50, 400)
    assert status_text(tmp_path, None) == "running the full suite · 50/400"
    reporter.failed("running the full suite stopped at 50 of 400")
    assert out.getvalue().splitlines()[-1] == "running the full suite stopped at 50 of 400"
    assert _file(tmp_path)["state"] == "failed"
    assert status_text(tmp_path, None) == ""                 # no longer shown as running


def test_failure_is_shown_even_when_it_comes_quickly(tmp_path: Path) -> None:
    clock, out = Clock(), Pipe()
    reporter = Reporter(tmp_path, None, "x", stream=out, clock=clock)
    clock.advance(0.5)
    reporter.failed("checking stopped")
    assert out.getvalue().strip() == "checking stopped"


def test_refresh_at_least_once_per_second(tmp_path: Path) -> None:
    clock, out = Clock(), Terminal()
    reporter = Reporter(tmp_path, None, "map", stream=out, clock=clock)
    clock.advance(2)
    reporter.update("building the test map")
    for _ in range(40):                                      # 10 more seconds, a call per 0.25 s
        clock.advance(0.25)
        reporter.update("building the test map")
    assert out.getvalue().count("\r") >= 10
    shown = out.getvalue().count("\r")
    clock.advance(1.2)                                       # no update at all, just the beat
    reporter.tick()
    assert out.getvalue().count("\r") == shown + 1
    assert out.getvalue().split("\r")[-1].startswith("building the test map")


def test_the_file_is_written_at_once_and_carries_the_writer(tmp_path: Path) -> None:
    Reporter(tmp_path, "s1", "read").update("reading your answer", 0, 0)
    data = _file(tmp_path, "s1")
    assert data["step"] == "reading your answer" and data["state"] == "running"
    assert data["kind"] == "read" and isinstance(data["pid"], int)
    assert status_text(tmp_path, "s1") == "reading your answer"


def test_no_stream_means_no_display_at_all(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    clock = Clock()
    reporter = Reporter(tmp_path, "s1", "read", clock=clock)
    clock.advance(30)
    reporter.update("reading your answer")
    reporter.done()
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""



@pytest.mark.sr("SR-232")
def test_failed_progress_write_is_retried_without_waiting(tmp_path, monkeypatch):
    import os

    reporter = Reporter(tmp_path, "s1", "judge", clock=Clock())
    replace = os.replace
    attempts = []

    def fail_once(src, dst):
        attempts.append(dst)
        if len(attempts) == 1:
            raise PermissionError("busy")
        return replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_once)
    reporter.update("judging", 1, 10)
    reporter.update("judging", 1, 10)
    reporter.update("judging", 1, 10)
    assert len(attempts) == 2
    assert _file(tmp_path, "s1")["done"] == 1
