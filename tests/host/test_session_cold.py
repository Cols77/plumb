"""SR-014: session start inside its budget on plumb's own records, cold and warm, and the
work it leaves out of the hook when the state is cold."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from plumb.api import open_core

pytestmark = pytest.mark.sr("SR-014")

REPO = Path(__file__).resolve().parents[2]
BUDGET_MS = 1400.0
STEPS = ("imports", "core_open", "index", "brief", "tests_summary", "snapshot", "tree_scan",
         "awareness", "triage_offer")

_HARNESS = """
import io, json, sys, time
start = time.monotonic()
from plumb.hosts.claude_code import session_start
out = io.StringIO()
session_start.main(stdin=io.StringIO(sys.argv[2]), stdout=out, root=sys.argv[1],
                   watchdog=False, start=start)
print(json.dumps({"ms": (time.monotonic() - start) * 1000, "out": out.getvalue()}))
"""
PAYLOAD = {"session_id": "cold", "transcript_path": "", "hook_event_name": "SessionStart"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


@pytest.fixture(scope="module")
def own_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A clone of this repository's committed state with the test map built once."""
    root = tmp_path_factory.mktemp("cold") / "plumb"
    try:
        _git(REPO, "rev-parse", "--git-dir")
        _git(root.parent, "clone", "-q", "--local", "-c", "core.autocrlf=false", str(REPO),
             str(root))
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    if not (root / ".plumb" / "requirements").is_dir():
        pytest.skip("no plumb records in this checkout")
    from plumb.verify.testmap import build_map

    build_map(open_core(root))
    return root


def _call(root: Path, env: dict[str, str] | None = None) -> tuple[str, float]:
    import os

    payload = json.dumps({**PAYLOAD, "cwd": str(root)})
    result = subprocess.run([sys.executable, "-c", _HARNESS, str(root), payload],
                            capture_output=True, text=True, encoding="utf-8", check=False,
                            timeout=60, env={**os.environ, **(env or {})})
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    return found["out"], found["ms"]


def _wipe_cache(root: Path) -> None:
    shutil.rmtree(root / ".plumb" / "cache", ignore_errors=True)


def test_cold_start_over_budget_today(own_copy: Path) -> None:
    """The plan's target: the best of four cold runs at most 0.9 of the budget."""
    runs = []
    for _ in range(4):
        _wipe_cache(own_copy)
        runs.append(_call(own_copy))
    best = min(ms for _, ms in runs)
    assert best <= BUDGET_MS * 0.9, f"cold session start {best:.0f} ms against {BUDGET_MS:.0f}"


def test_timing_file_names_every_step(own_copy: Path) -> None:
    _call(own_copy, {"PLUMB_HOOK_TIMING": "1"})
    data = json.loads((own_copy / ".plumb" / "session" / "cold" / "timing.json")
                      .read_text("utf-8"))
    assert set(STEPS) <= set(data["steps"])
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data["steps"].values())


def test_timing_off_writes_nothing(repo: Path, hook_input,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from fakes import FakeVerify

    from plumb.hosts.claude_code import session_start

    monkeypatch.delenv("PLUMB_HOOK_TIMING", raising=False)
    session_start.main(stdin=io.StringIO(hook_input("SessionStart")), stdout=io.StringIO(),
                       root=repo, verify=FakeVerify())
    assert not list((repo / ".plumb" / "session").glob("*/timing.json"))
