"""SR-344, SR-345: one benchmark run: a scratch repository adopted by plumb, a cheap model
working through the task's requests one turn each, the scripted owner answering what it asks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plumb.evaluate import issues as issues_mod
from plumb.evaluate import score as score_mod

TURN_CAP = 25            # --max-turns per request
OWNER_CAP = 3            # exchanges per request
RUN_CAP_S = 20 * 60      # per run
# what the agent may run unasked in the scratch repository (headless: nobody answers a prompt)
ALLOWED_TOOLS = ("Bash(python:*)", "Bash(python3:*)", "Bash(plumb:*)", "Bash(git:*)",
                 "Bash(pytest:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(echo:*)")


@dataclass
class Turn:
    role: str            # owner | agent
    text: str
    request: int         # 1-based index of the scripted request this turn belongs to
    source: str = ""     # owner: "script" | "scripted-owner"; agent: "" | "capped" | "error"


@dataclass
class RunResult:
    run_dir: Path
    scratch: Path
    score: dict
    issues: list[dict]
    unanswered: int


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   encoding="utf-8")


def scratch_repo(parent: Path) -> Path:
    """A git repository with a first commit (so hooks work), adopted by plumb with the Claude
    Code hooks installed (the owner's choice, DEC-306)."""
    from plumb.commands import init_repo
    from plumb.hosts.claude_code import install

    root = Path(parent) / "scratch"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "eval@example.com")
    _git(root, "config", "user.name", "Eval")
    _git(root, "commit", "-q", "--allow-empty", "-m", "initial")
    init_repo(root)
    install.install(root)
    return root


def claude_turn(binary: str, scratch: Path, message: str, *, model: str, session_id: str | None,
                system: str, timeout_s: float, env: dict[str, str] | None = None
                ) -> dict[str, Any]:
    """One headless ``claude -p`` call in the scratch repository."""
    argv = [binary, "-p", "--model", model, "--output-format", "json",
            "--max-turns", str(TURN_CAP), "--permission-mode", "acceptEdits",
            "--setting-sources", "project", "--append-system-prompt", system,
            *(["--resume", session_id] if session_id else []),
            "--allowedTools", *ALLOWED_TOOLS]
    env = {k: v for k, v in (os.environ if env is None else env).items()
           if k not in ("PLUMB_JOB", "PLUMB_WORKER")}
    # the agent's shell finds the plumb command of the interpreter running the benchmark
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    out = {"text": "", "session_id": session_id, "capped": False, "error": ""}
    try:
        done = subprocess.run(argv, input=message, capture_output=True, text=True,
                              encoding="utf-8", cwd=scratch, env=env, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {**out, "capped": True, "error": "the call ran out of time"}
    except OSError as exc:
        return {**out, "error": str(exc)}
    try:
        data = json.loads(done.stdout)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return {**out, "error": (done.stderr or done.stdout).strip()[:300]
                or f"exit code {done.returncode}"}
    text = str(data.get("result") or "")
    maxed = "max_turns" in str(data.get("subtype", "")) or "max turns" in text.lower()
    return {"text": text, "session_id": data.get("session_id") or session_id,
            "capped": maxed or int(data.get("num_turns") or 0) >= TURN_CAP,
            "error": text[:300] if data.get("is_error") and not maxed else ""}


def run_task(root: Path, task: Any, *, model: str, owner: Any, runs_dir: Path | None = None,
             claude=claude_turn, now=time.monotonic, binary: str | None = None) -> RunResult:
    binary = binary or shutil.which("claude")
    if binary is None:   # raised before any folder is made (SR-344 EX-3)
        raise RuntimeError("the claude command was not found on this machine")
    root = Path(root)
    run_dir = (runs_dir or root / ".plumb" / "eval" / "runs") / (
        f"{time.strftime('%Y%m%dT%H%M%S')}-{task.name}-{model}")
    run_dir.mkdir(parents=True)
    scratch = scratch_repo(Path(tempfile.mkdtemp(prefix="plumb-eval-")))
    transcript: list[Turn] = []
    state: dict[str, Any] = {"session": None, "start": now(), "out_of_time": False}

    def send(n: int, message: str, source: str) -> Turn:
        transcript.append(Turn("owner", message, n, source))
        left = RUN_CAP_S - (now() - state["start"])
        if left <= 0:
            state["out_of_time"] = True
            turn = Turn("agent", "", n, "capped")
        else:
            got = claude(binary, scratch, message, model=model, session_id=state["session"],
                         system=task.agent_brief, timeout_s=left, env=None)
            state["session"] = got.get("session_id") or state["session"]
            turn = Turn("agent", got.get("text") or got.get("error") or "", n,
                        "capped" if got.get("capped") else "error" if got.get("error") else "")
        transcript.append(turn)
        return turn

    unanswered = 0
    for n, request in enumerate(task.requests, 1):
        reply = send(n, request, "script")
        sent = 0
        while reply.source == "":   # a capped or failed reply is not put to the owner
            verdict = owner.answer(task.owner_brief, request, reply.text)
            if not verdict["asks"]:
                break
            if sent == OWNER_CAP:
                unanswered += 1
                break
            reply = send(n, verdict["answer"], "scripted-owner")
            sent += 1
        if state["out_of_time"]:
            break
    issues = issues_mod.collect(scratch, run_dir, root, run_dir.name, task.name, model)
    shutil.copytree(scratch / ".plumb", run_dir / "plumb", dirs_exist_ok=True)
    (run_dir / "transcript.jsonl").write_text(
        "".join(json.dumps(asdict(t), ensure_ascii=False) + "\n" for t in transcript),
        encoding="utf-8")
    score = score_mod.checks(scratch, task) | score_mod.trail(scratch, transcript, issues,
                                                              unanswered)
    (run_dir / "score.json").write_text(json.dumps(score, indent=1), encoding="utf-8")
    print(score_mod.line(task.name, model, score))
    return RunResult(run_dir, scratch, score, issues, unanswered)
