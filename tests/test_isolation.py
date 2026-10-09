"""Tests do not depend on where they run (owner intent INT-027)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROBE = "ISOLATION_PROBE_ACTIVE"


@pytest.mark.skipif(not os.environ.get(_PROBE), reason="run only by the outer test below")
def test_probe_sees_none_of_the_outer_environment(tmp_path: Path) -> None:
    leaked = [n for n in os.environ if n.startswith(("CLAUDE_", "PLUMB_AGENT", "TYPESAFE_",
                                                     "OPENROUTER_", "CODEX_"))]
    assert leaked == []
    assert Path(os.environ["USERPROFILE"]) == Path(os.environ["HOME"])
    assert os.environ["HOME"] != os.environ["ISOLATION_OUTER_HOME"]  # a temp dir
    assert Path.home() == Path(os.environ["HOME"])
    assert os.environ["PLUMB_HOME"] == os.environ["HOME"]


@pytest.mark.sr("SR-005")
def test_variables_set_outside_are_not_seen_inside_a_test() -> None:
    outer_home = str(Path(__file__).resolve().parent)
    env = dict(os.environ, **{
        _PROBE: "1", "CLAUDE_PROJECT_DIR": "x", "PLUMB_AGENT_SESSION": "s",
        "PLUMB_SESSION_ID": "s", "TYPESAFE_API_KEY": "k", "OPENROUTER_API_KEY": "k",
        "CODEX_HOME": "x", "ISOLATION_OUTER_HOME": outer_home,
        "HOME": outer_home, "USERPROFILE": outer_home})
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider",
         f"{__file__}::test_probe_sees_none_of_the_outer_environment"],
        env=env, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert " passed" in result.stdout and "skipped" not in result.stdout, result.stdout
