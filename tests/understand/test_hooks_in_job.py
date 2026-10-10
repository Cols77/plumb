"""SR-104 EX-2: a hook that runs inside a job's own session exits at once and queues nothing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from plumb.api import Core
from plumb.understand import jobs, queue, worker

pytestmark = pytest.mark.sr("SR-104")

HOOKS = ("session-start", "prompt", "post-edit", "stop", "pre-tool")


def _tree(root: Path) -> dict[str, int]:
    return {str(p.relative_to(root)): p.stat().st_size for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.parts}


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PLUMB_", "CLAUDE_"))}
    env.update(PLUMB_JOB="read-0123456789abcdef", PYTHONUTF8="1")
    return env


def test_ex2_hooks_exit_in_a_job_session(repo: Path) -> None:
    before = _tree(repo)
    for name in HOOKS:
        payload = {"session_id": "s1", "cwd": str(repo), "transcript_path": "",
                   "prompt": "yes, that is right", "tool_name": "Edit",
                   "tool_input": {"file_path": str(repo / "x.py")}, "source": "startup"}
        done = subprocess.run(
            [sys.executable, "-m", "plumb", "hook", name, "--root", str(repo)],
            input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
            cwd=repo, env=_env(), timeout=60)
        assert done.returncode == 0, name
        assert done.stdout == "", name
    assert _tree(repo) == before                            # nothing written
    assert not (repo / ".plumb" / "session" / "s1" / "jobs").exists()   # nothing queued


def test_queue_refuses_inside_a_job(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    monkeypatch.setattr(worker, "start_detached", lambda root, session: started.append(session))
    monkeypatch.setenv("PLUMB_JOB", "read-0123456789abcdef")
    core = Core(repo)
    job = jobs.new_job("read", "s1", "read.v1", {"n": 1})
    assert queue.enqueue(core, job) is None
    assert not jobs.job_path(repo, "s1", job.id).exists() and started == []
    assert queue.retry_failed(core, "s1") == []
