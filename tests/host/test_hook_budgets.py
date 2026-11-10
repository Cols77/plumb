"""SR-375: each hook's limits come from a profile of its steps on this repository; a cut is a
defect with a debug case; the owner's "hooks may take longer" changes the hard limit only."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_stop_stale import NODE, _verify, edit, project, run_stop, start_turn  # noqa: F401

from iaso.config import DEFAULT_HOOK_BUDGET_MS, load_config
from iaso.hosts.claude_code import hookio

pytestmark = pytest.mark.sr("SR-375")

PROFILE = Path(__file__).resolve().parents[2] / "docs" / "plans" / "2026-10-26-hook-profile.md"
ROW = re.compile(r"^\|\s*(?P<hook>[a-z-]+)\s*\|\s*(?P<key>[a-z_]+|-)\s*\|\s*(?P<runs>\d+)\s*\|"
                 r"\s*(?P<p50>[\d.]+)\s*\|\s*(?P<p95>[\d.]+)\s*\|", re.M)


def _profiled() -> dict[str, float]:
    """The p95 (ms, in-process) of each budget key in the profile table."""
    return {m["key"]: float(m["p95"]) for m in ROW.finditer(PROFILE.read_text("utf-8"))
            if m["key"] != "-"}


def test_ex1_a_profiled_stop_records_the_time_of_each_step(
        project: Path, hook_input, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setenv(hookio.PROFILE_ENV, "1")
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    run_stop(project, hook_input, verify=_verify())
    lines = (project / ".iaso" / "session" / hookio.PROFILE_FILE).read_text("utf-8")
    entry = json.loads(lines.splitlines()[-1])
    steps = [name for name, _ in entry["steps"]]
    assert entry["hook"] == "stop" and entry["total_ms"] > 0 and not entry["cut"]
    for step in ("record index", "changed paths", "records", "covering tests", "next action"):
        assert step in steps, step


def test_ex1_the_profile_is_measured_and_the_limits_stay_at_60_90_until_reprofiled() -> None:
    """The profile table covers every budget key; the limits stay at 60 s / 90 s until the logs
    are compacted at INT-114's landing and the hooks are profiled again (DEC-397)."""
    assert set(_profiled()) == set(DEFAULT_HOOK_BUDGET_MS)
    assert "DEC-397" in PROFILE.read_text("utf-8")
    assert dict(DEFAULT_HOOK_BUDGET_MS) == {
        "session_start": 60000, "prompt": 60000, "stop": 60000, "post_edit": 15000}
    assert hookio.HARD_LIMIT_S == 90.0


_SLOW = """import io, sys, time
sys.path.insert(0, r"{tests}")
from fakes import FakeVerify
from iaso.hosts.claude_code import stop

class Slow(FakeVerify):
    def select(self, changed, *, budget_s=None):
        time.sleep(20)

stop.main(stdin=io.StringIO({payload!r}), stdout=sys.stdout, root=r"{repo}",
          watchdog=True, start=time.monotonic(), verify=Slow(nodes=("{node}",)))
"""


def test_ex2_a_hook_needing_twenty_seconds_is_cut_and_opens_one_debug_case(
        project: Path, hook_input, tmp_path: Path) -> None:  # noqa: F811
    from iaso import debug
    from iaso.understand.summary import AFTER_STOP

    (project / ".iaso" / "config.yaml").write_text("hooks:\n  hard_limit_s: 2\n",
                                                    encoding="utf-8")
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    script = tmp_path / "slow.py"
    script.write_text(_SLOW.format(tests=Path(__file__).parent, repo=project, node=NODE,
                                   payload=hook_input("Stop", session_id="s1")), "utf-8")
    began = time.monotonic()
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                            timeout=60, check=False)
    assert time.monotonic() - began < 15                      # cut at the hard limit, not 20 s
    assert json.loads(result.stdout)["systemMessage"].endswith(hookio.SKIP_BUDGET)
    assert (project / ".iaso" / "session" / "s1" / AFTER_STOP).is_file()   # the worker's part
    cases = [c for c in debug.all_cases(project) if c.get("kind") == "hook-error"]
    assert [c["target"] for c in cases] == ["stop"]
    assert "hard limit 2.0s" in (project / ".iaso/session/errors.log").read_text("utf-8")


def test_ex4_hooks_may_take_longer_changes_the_hard_limit_and_nothing_else(
        repo: Path) -> None:
    import dataclasses

    config = repo / ".iaso" / "config.yaml"
    config.write_text("verify:\n  turn_budget_s: 45\n", "utf-8")
    before = load_config(repo)
    config.write_text("verify:\n  turn_budget_s: 45\nhooks:\n  hard_limit_s: 120\n", "utf-8")
    after = load_config(repo)
    assert hookio.hard_limit_s(repo) == 120.0 != hookio.HARD_LIMIT_S
    assert dataclasses.replace(after, hooks=dataclasses.replace(
        after.hooks, hard_limit_s=before.hooks.hard_limit_s)) == before
