"""SR-386: the one-heavy-job lock taken by the commands themselves, and the landing queue."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[2] / "src")


def run(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": SRC, "IASO_HEAVY_WAIT_S": "0.1"}
    return subprocess.run([sys.executable, "-m", "iaso", *args], cwd=repo, env=env,
                          capture_output=True, text=True, encoding="utf-8", **kw)


def popen(repo: Path, *args: str) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": SRC, "IASO_HEAVY_WAIT_S": "0.1"}
    return subprocess.Popen([sys.executable, "-m", "iaso", *args], cwd=repo, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8")


@pytest.fixture
def gitrepo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.mark.sr("SR-386")
def test_second_heavy_command_waits_for_the_first_and_says_so_once(gitrepo: Path) -> None:
    """EX-1: B waits, says once what it waits for, starts when A's run ends."""
    lock = gitrepo / ".git" / "iaso-heavy.lock"
    marker = gitrepo / "a-done"
    a = popen(gitrepo, "heavy", "--", sys.executable, "-c",
              f"import time, pathlib; time.sleep(2); pathlib.Path(r'{marker}').write_text('x')")
    for _ in range(100):
        if lock.exists():
            break
        time.sleep(0.05)
    assert lock.exists()
    first, pid_line = lock.read_text(encoding="utf-8").splitlines()[:2]
    assert pid_line.startswith("pid ")
    b = run(gitrepo, "heavy", "--", sys.executable, "-c",
            f"import pathlib; print('B saw A done:', pathlib.Path(r'{marker}').exists())")
    a.communicate()
    assert b.returncode == 0 and "B saw A done: True" in b.stdout
    assert b.stderr.count(first) == 1
    assert not lock.exists()


@pytest.mark.sr("SR-386")
def test_a_lock_of_a_dead_process_is_taken_over_and_said_once(gitrepo: Path) -> None:
    """EX-2: the lock names a process no longer running."""
    lock = gitrepo / ".git" / "iaso-heavy.lock"
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True)
    dead = done.stdout.strip()
    lock.write_text(f"old job\npid {dead}\n", encoding="utf-8")
    r = run(gitrepo, "heavy", "--", sys.executable, "-c", "print('ran')", timeout=30)
    assert r.returncode == 0 and "ran" in r.stdout
    assert r.stderr.count(dead) == 1
    assert not lock.exists()


@pytest.mark.sr("SR-386")
def test_no_lock_held_runs_at_once_and_says_nothing(gitrepo: Path, capsys) -> None:
    """EX-3: in process, no lock held."""
    from iaso.heavy import heavy

    lock = gitrepo / ".git" / "iaso-heavy.lock"
    with heavy(gitrepo, "a job"):
        assert lock.read_text(encoding="utf-8").splitlines()[0] == "a job"
        assert os.environ.get("IASO_HEAVY_HELD") == "1"
    out = capsys.readouterr()
    assert out.out == "" and out.err == "" and not lock.exists()
    assert "IASO_HEAVY_HELD" not in os.environ


@pytest.mark.sr("SR-386")
def test_two_queued_branches_land_one_at_a_time_and_the_board_shows_both(gitrepo: Path) -> None:
    """EX-4: the second waits while the first is landing; the board shows both."""
    assert run(gitrepo, "landing", "add", "intent/a", "--session", "s-a").returncode == 0
    assert run(gitrepo, "landing", "add", "intent/b", "--session", "s-b").returncode == 0
    assert run(gitrepo, "landing", "add", "intent/b").returncode == 0     # twice: no change
    first = run(gitrepo, "landing", "next")
    assert first.returncode == 0 and first.stdout.strip() == "intent/a"
    second = run(gitrepo, "landing", "next")
    assert second.returncode != 0 and "intent/a" in second.stdout + second.stderr
    board = run(gitrepo, "landing").stdout
    assert "intent/a" in board and "landing" in board and "s-a" in board
    assert "intent/b" in board and "waiting" in board and "s-b" in board
    assert board.count("intent/b") == 1
    assert run(gitrepo, "landing", "done", "intent/a").returncode == 0
    assert run(gitrepo, "landing", "next").stdout.strip() == "intent/b"


@pytest.mark.sr("SR-386")
def test_a_branch_waiting_on_the_owner_does_not_hold_the_next(gitrepo: Path) -> None:
    """EX-5: the first waits on the owner, the next lands; main mid-merge refuses."""
    run(gitrepo, "landing", "add", "intent/a", "--session", "s-a")
    run(gitrepo, "landing", "add", "intent/b", "--session", "s-b")
    assert run(gitrepo, "landing", "wait", "intent/a", "--on", "an answer on SR-9").returncode == 0
    (gitrepo / ".git" / "MERGE_HEAD").write_text("0" * 40 + "\n", encoding="utf-8")
    held = run(gitrepo, "landing", "next")
    assert held.returncode != 0 and "merge" in (held.stdout + held.stderr).lower()
    (gitrepo / ".git" / "MERGE_HEAD").unlink()
    assert run(gitrepo, "landing", "next").stdout.strip() == "intent/b"
    board = run(gitrepo, "landing").stdout
    assert "an answer on SR-9" in board and "owner" in board
    assert run(gitrepo, "landing", "ready", "intent/a").returncode == 0
    assert "an answer on SR-9" not in run(gitrepo, "landing").stdout


@pytest.mark.sr("SR-386")
def test_status_prints_the_board_only_when_the_queue_is_not_empty(gitrepo: Path) -> None:
    """Item 10: status ends with the board; an empty queue adds nothing."""
    assert "intent/a" not in run(gitrepo, "status").stdout
    run(gitrepo, "landing", "add", "intent/a", "--session", "s-a")
    out = run(gitrepo, "status")
    assert "intent/a" in out.stdout and "s-a" in out.stdout, out.stderr
