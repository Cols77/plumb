"""``Session(repo)``: drives the real hooks as subprocesses against a repository, with a fake
dispatcher (docs/plans/sp8-plan.md 3.2 item 9).

The fake dispatcher is handed to the child processes as a script file named by
``PLUMB_FAKE_DISPATCH`` (``{kind: answer}`` JSON); ENGINE's ``dispatch.configured`` honours it
when the variable is set. Every hook runs as ``python -m plumb hook <name>`` with the host's
JSON on stdin.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class Session:
    def __init__(self, repo: Path, *, session_id: str = "harness",
                 script: Mapping[str, Any] | None = None) -> None:
        self.repo = Path(repo)
        self.session_id = session_id
        self.script_path = self.repo / ".plumb" / "cache" / "fake_dispatch.json"
        self.script_path.parent.mkdir(parents=True, exist_ok=True)
        self.script_path.write_text(json.dumps(dict(script or {})), encoding="utf-8")
        self.outputs: list[str] = []

    # -- plumbing
    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("PLUMB_", "CLAUDE_"))}
        env.update(PLUMB_FAKE_DISPATCH=str(self.script_path),
                   CLAUDE_PROJECT_DIR=str(self.repo), PYTHONUTF8="1")
        return env

    def hook(self, name: str, **fields: Any) -> str:
        payload = {"session_id": self.session_id, "cwd": str(self.repo),
                   "transcript_path": "", **fields}
        done = subprocess.run(
            [sys.executable, "-m", "plumb", "hook", name, "--root", str(self.repo)],
            input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
            cwd=self.repo, env=self.env(), timeout=60)
        self.outputs.append(done.stdout)
        return done.stdout

    # -- what an owner and an agent do
    def start(self) -> str:
        return self.hook("session-start", hook_event_name="SessionStart", source="startup")

    def say(self, text: str) -> str:
        """The owner's message (the prompt hook)."""
        return self.hook("prompt", hook_event_name="UserPromptSubmit", prompt=text)

    def edit(self, path: str, content: str = "x = 1\n") -> str:
        """The agent edits a file (the post-edit hook)."""
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self.hook("post-edit", hook_event_name="PostToolUse", tool_name="Edit",
                         tool_input={"file_path": str(target)})

    def stop(self) -> str:
        """The end of the agent's turn (the stop hook)."""
        return self.hook("stop", hook_event_name="Stop")

    # -- the worker and the status line
    def _names(self, folder: str) -> set[str]:
        base = self.repo / ".plumb" / "session" / self.session_id / folder
        return {p.stem for p in base.glob("*.json")} if base.is_dir() else set()

    def worker_idle(self, timeout_s: float = 20.0) -> bool:
        """True once every queued job has a result (the worker has nothing left to do)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._names("jobs") <= self._names("results"):
                return True
            time.sleep(0.1)
        return False

    def status_line(self) -> str:
        done = subprocess.run(
            [sys.executable, "-m", "plumb", "statusline", "--root", str(self.repo)],
            input=json.dumps({"session_id": self.session_id, "cwd": str(self.repo)}),
            capture_output=True, text=True, encoding="utf-8", cwd=self.repo, env=self.env(),
            timeout=60)
        return done.stdout.strip()
