"""Hidden checks of the simple task: run from the repository root, drive game.py on stdin."""

import subprocess
import sys


def play(*moves: str) -> str:
    done = subprocess.run([sys.executable, "game.py"], input="".join(m + "\n" for m in moves),
                          capture_output=True, text=True, timeout=20)
    return done.stdout


# request: 1
def test_x_wins():
    assert "X wins" in play("1", "4", "2", "5", "3")


# request: 1
def test_o_wins():
    assert "O wins" in play("1", "4", "2", "5", "9", "6")


# request: 1
def test_invalid_then_valid():
    out = play("x", "1", "1", "4", "2", "5", "3")
    assert out.count("invalid") == 2 and "X wins" in out


# request: 2
def test_draw_then_fresh_board():
    out = play("1", "2", "3", "5", "4", "6", "8", "7", "9", "1", "4", "2", "5", "3")
    assert "draw" in out and "X wins" in out.split("draw", 1)[1]


# request: 3
def test_score_after_win():
    assert "score X 1 O 0" in play("1", "4", "2", "5", "3")


# request: 3
def test_empty_line_quits():
    done = subprocess.run([sys.executable, "game.py"], input="\n", capture_output=True,
                          text=True, timeout=20)
    assert done.returncode == 0
