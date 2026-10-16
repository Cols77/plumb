"""SR-181: the hook watchdog's hard limit and the soft budgets are settings with defaults
that survive a loaded machine."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from plumb.config import DEFAULT_HOOK_BUDGET_MS, HooksConfig, load_config
from plumb.hosts.claude_code import hookio

pytestmark = pytest.mark.sr("SR-181")


def _run(handler, repo: Path, **kwargs) -> str:
    out = io.StringIO()
    hookio.run_hook("test", handler, stdin=io.StringIO("{}"), stdout=out, root=repo, **kwargs)
    return out.getvalue()


def test_a_hook_taking_four_seconds_is_not_cut(repo: Path) -> None:
    """EX-1: the defaults leave a loaded machine's 4 s hook alone (the clock is moved, not
    waited for)."""
    clock = time.monotonic() - 3.6  # the hook started 3.6 s ago: about 4 s, past the old 1.9 s

    def handler(ctx):
        ctx.deadline.check("late step")
        return hookio.HookOutput(text="plumb: checked")

    out = _run(handler, repo, budget_ms=hookio.hook_budget("prompt"), watchdog=True,
               start=clock)
    assert out.splitlines() == ["plumb: checked"]
    assert hookio.hard_limit_s(repo) > 4.0
    assert HooksConfig().budget_ms["prompt"] > 3500


def test_the_hard_limit_still_cuts_at_the_configured_value(repo: Path, tmp_path: Path) -> None:
    """EX-2: a hook that never answers is cut at hooks.hard_limit_s."""
    (repo / ".plumb" / "config.yaml").write_text("hooks:\n  hard_limit_s: 0.4\n",
                                                 encoding="utf-8")
    script = tmp_path / "cut.py"
    script.write_text(
        "import io, sys, time\n"
        "from plumb.hosts.claude_code import hookio\n"
        "def h(ctx):\n    time.sleep(5)\n"
        "t = time.monotonic()\n"
        f"hookio.run_hook('t', h, stdin=io.StringIO('{{}}'), stdout=sys.stdout, root=r'{repo}',\n"
        "                budget_ms=60000, watchdog=True, start=t)\n", encoding="utf-8")
    began = time.monotonic()
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                            timeout=30, check=False)
    assert result.stdout.splitlines() == [hookio.SKIP_BUDGET]
    assert time.monotonic() - began < 4.5
    assert "hard limit 0.4s" in (repo / ".plumb/session/errors.log").read_text("utf-8")


def test_the_settings_are_read_from_config_yaml(repo: Path) -> None:
    """EX-3: configured values win; unset ones fall back to the defaults."""
    assert hookio.hard_limit_s(repo) == hookio.HARD_LIMIT_S == 30.0
    (repo / ".plumb" / "config.yaml").write_text(
        "hooks:\n  hard_limit_s: 3.5\n  budget_ms: {stop: 2500}\n", encoding="utf-8")
    hooks = load_config(repo).hooks
    assert hooks.hard_limit_s == 3.5
    assert hooks.budget_ms["stop"] == 2500
    assert hooks.budget_ms["prompt"] == DEFAULT_HOOK_BUDGET_MS["prompt"]
    assert hookio.hard_limit_s(repo) == 3.5


def test_host_timeouts_sit_above_the_hard_limit_and_grace() -> None:
    """EX-4: the plugin bundle's hook timeouts exceed the default limit plus the stop grace."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import build_plugin
    from plumb.hosts.claude_code.stop import STOP_GRACE_S

    hooks = json.loads(build_plugin.hooks_json())["hooks"]
    timeouts = [h["timeout"] for groups in hooks.values() for g in groups for h in g["hooks"]]
    assert min(timeouts) > hookio.HARD_LIMIT_S + STOP_GRACE_S
    budgets = HooksConfig().budget_ms
    assert all(v < hookio.HARD_LIMIT_S * 1000 for v in budgets.values())
