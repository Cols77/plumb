"""SR-346: the score of one run."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.evaluate import score
from plumb.evaluate.run import Turn
from plumb.evaluate.tasks import Task

pytestmark = pytest.mark.sr("SR-346")

CHECKS = '''\
import subprocess, sys

def play(moves):
    return subprocess.run([sys.executable, "game.py"], input=moves, capture_output=True,
                          text=True).stdout

def test_x_wins():
    assert "X wins" in play("1\\n4\\n2\\n5\\n3\\n")

def test_o_wins():
    assert "O wins" in play("1\\n4\\n2\\n5\\n9\\n6\\n")

def test_invalid():
    assert "invalid" in play("1\\n1\\n")

def test_score_line():
    assert "score X 1 O 0" in play("1\\n4\\n2\\n5\\n3\\n")

def test_quit():
    assert play("\\n") is not None

def test_draw():
    assert "draw" in play("1\\n2\\n3\\n5\\n4\\n6\\n8\\n7\\n9\\n")
'''


def make_task(tmp_path: Path) -> Task:
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_game.py").write_text(CHECKS, encoding="utf-8")
    return Task("simple", "agent", "owner", ["r1"], checks)


def test_a_game_that_never_draws_misses_the_draw_check(tmp_path, reference_game):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "game.py").write_text(reference_game.replace('print("draw")', "pass"),
                                     encoding="utf-8")
    result = score.checks(scratch, make_task(tmp_path))
    assert (result["checks_passed"], result["checks_total"]) == (5, 6)
    assert result["failed"] == ["test_draw"]
    assert not (scratch / "eval_checks").exists()


def test_the_trail_counts_gates_and_proofs(repo, write_record):
    from plumb.api import open_core
    from plumb.capture.proof import set_evidence

    for n in (1, 2):
        write_record(repo, f"---\nid: SR-{n:03d}\ntitle: Requirement {n}\nfeature: FEAT-001\n"
                           f"statement: s\nexamples:\n- id: EX-1\n  given: a\n  when: b\n"
                           f"  then: c\n---\n")
    core = open_core(repo)
    for stage in ("clarify", "plan"):
        core.log_append("events", "intent-gate", {"intent": "INT-001", "digest": "d",
                                                  "stage": stage, "findings": 0})
    set_evidence(core, "SR-001", "https://x.test/run", "it worked", passed=True)
    turns = [Turn("owner", "q", 1, "scripted-owner"), Turn("agent", "a", 1, "")]
    got = score.trail(repo, turns, [{"command": "c"}], unanswered=1)
    assert (got["gates"], got["proofs"], got["records"]) == (2, 1, 2)
    assert (got["questions_asked"], got["questions_answered"], got["issues"]) == (2, 1, 1)


def test_line_renders_the_score():
    got = {"checks_passed": 5, "checks_total": 6, "records": 7, "questions_asked": 2,
           "questions_answered": 2, "gates": 2, "stale": 0, "issues": 3}
    assert score.line("simple", "haiku", got) == (
        "simple haiku: checks 5/6, records 7, questions 2/2, gates 2, stale 0, issues 3")
