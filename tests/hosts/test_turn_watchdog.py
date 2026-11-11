"""``iaso turn start`` never drops the owner's message when the brief reaches the watchdog
(audit round 3, R13 Q4).

The CLI-only fallback runs the session brief and the prompt event in one process; the
watchdog ends the process (``os._exit``) at its hard limit. The prompt is now logged and the
turn started (``turn.json``) first, so a brief cut by the watchdog costs only the brief. One
test per entry point that reaches the watchdog: the first ``turn start`` (stdin, and
``--prompt-file`` as the Codex, Pi and Hermes instruction blocks may use it) and a later
``turn start`` of the same session. Each runs in a subprocess (the watchdog exits the
process) whose session brief is forced past a short hard limit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hosts_helpers import make_project

pytestmark = pytest.mark.sr("SR-282")

# The brief sleeps past its watchdog (cut to 0.3 s for the session-start event only) and
# notes each call; the prompt event keeps the real limit.
SCRIPT = r"""
import sys, time
from pathlib import Path
import iaso.hosts.claude_code.hookio as hookio
import iaso.hosts.claude_code.session_start as session_start

real_run_hook, real_handle = hookio.run_hook, session_start.handle

def run_hook(name, handler, **kwargs):
    hookio.HARD_LIMIT_S = 0.3 if name == "session-start" else 1.9
    return real_run_hook(name, handler, **kwargs)

def slow_brief(ctx, **kwargs):
    with open(Path(ctx.root) / "brief-calls.txt", "a", encoding="utf-8") as handle:
        handle.write("brief\n")
    time.sleep(3)
    return real_handle(ctx, **kwargs)

hookio.run_hook = run_hook
session_start.handle = slow_brief
from iaso.cli import main
sys.exit(main(sys.argv[1:]))
"""


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    return make_project(repo, write_record)


def _turn_start(repo: Path, words: str, *extra: str, stdin: bool = True) -> str:
    env = {k: v for k, v in os.environ.items() if k != "IASO_AGENT_SESSION"}
    result = subprocess.run([sys.executable, "-c", SCRIPT, "turn", "start", "--session",
                             "c9", "--root", str(repo), *extra],
                            input=words.encode("utf-8") if stdin else b"", cwd=repo,
                            env=env, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8", "replace")


def _prompts(repo: Path) -> list[dict]:
    path = repo / ".iaso" / "session" / "prompts.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def _assert_logged(repo: Path, words: str, count: int) -> None:
    prompts = _prompts(repo)
    assert len(prompts) == count
    assert prompts[-1]["text"] == words and prompts[-1]["via"] == "turn"
    turn = json.loads((repo / ".iaso" / "session" / "c9" / "turn.json").read_text("utf-8"))
    assert turn["prompt_digest"] == prompts[-1]["digest"]


def _watchdog_fired(repo: Path) -> bool:
    log = repo / ".iaso" / "session" / "errors.log"
    return log.exists() and "watchdog: hard limit" in log.read_text("utf-8")


def _brief_calls(repo: Path) -> int:
    path = repo / "brief-calls.txt"
    return len(path.read_text("utf-8").splitlines()) if path.exists() else 0


def test_first_turn_start_logs_the_prompt_when_the_brief_hits_the_watchdog(
        project: Path) -> None:
    out = _turn_start(project, "please make SR-001 handle floats")
    assert _watchdog_fired(project) and _brief_calls(project) == 1
    _assert_logged(project, "please make SR-001 handle floats", 1)
    assert "SR-001" in out  # the prompt event's records reached the agent before the cut


def test_first_turn_start_from_a_prompt_file_logs_the_prompt(project: Path,
                                                             tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("ok, carry on", encoding="utf-8")
    _turn_start(project, "", "--prompt-file", str(prompt), stdin=False)
    assert _watchdog_fired(project)
    _assert_logged(project, "ok, carry on", 1)


def test_later_turn_start_logs_the_prompt_and_does_not_repeat_the_brief(
        project: Path) -> None:
    _turn_start(project, "change add")
    _turn_start(project, "ok, go ahead")
    assert _brief_calls(project) == 1  # the first turn started: the brief is not repeated
    _assert_logged(project, "ok, go ahead", 2)
