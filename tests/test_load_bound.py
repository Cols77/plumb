"""SR-307: load-bound tests wait for a free CPU and are reported, not failed, on a missed budget."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import loadbound
import pytest

pytestmark = pytest.mark.sr("SR-307")

_TESTS = Path(__file__).resolve().parent


def test_ex1_it_waits_until_the_cpu_is_below_50_percent() -> None:
    readings = iter([90.0, 90.0, 20.0])
    calls: list[float] = []
    assert loadbound.wait_for_free_cpu(lambda: calls.append(1) or next(readings))
    assert len(calls) == 3


def test_ex4_after_the_limit_it_gives_up_and_runs_anyway() -> None:
    now = iter(range(0, 1000, 100))
    assert not loadbound.wait_for_free_cpu(lambda: 95.0, limit=300, clock=lambda: next(now))


def _suite(repo: Path, body: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
    (repo / "test_t.py").write_text(
        "import pytest\npytestmark = pytest.mark.load_bound\n" + body, encoding="utf-8")
    (repo / "conftest.py").write_text(
        "import loadbound\nloadbound.cpu_busy = lambda: 1.0\n"
        "loadbound.wait_for_free_cpu.__defaults__ = (lambda: 1.0, 300, lambda: 0.0)\n"
        "pytest_plugins = ['loadbound']\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(_TESTS.parent / "src"), str(_TESTS)])}
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rx",
                           "--rootdir", str(repo), "-c", "NUL" if os.name == "nt" else "/dev/null",
                           str(repo / "test_t.py")], cwd=repo, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=False)
    cases = [row for p in (repo / ".plumb" / "cache" / "debug").glob("*.json")
             for row in json.loads(p.read_text(encoding="utf-8"))]
    return done, cases


def test_ex2_a_missed_time_budget_is_load_bound_with_one_debug_case(repo: Path) -> None:
    done, cases = _suite(repo, "def test_t():\n    assert 9 < 1, 'took 9 ms, 1 ms budget'\n")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "xfailed" in done.stdout
    assert [(c["kind"], c["state"]) for c in cases] == [("load-bound test", "open")]
    assert "test_t.py::test_t" in cases[0]["target"]


def test_ex3_another_failed_assertion_fails_as_usual(repo: Path) -> None:
    done, cases = _suite(repo, "def test_t():\n    assert [1] == [2], 'wrong answer'\n")
    assert done.returncode == 1 and "failed" in done.stdout
    assert cases == []
