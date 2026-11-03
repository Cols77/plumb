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

from plumb.evaluate import ask_server
from plumb.evaluate import issues as issues_mod
from plumb.evaluate import score as score_mod
from plumb.hosts.claude_code import ask_gate

# DEC-308: the owner chose no limits by default; each limit is set only when named (None: none)
NO_LIMITS = {"exchanges": None, "turns": None, "minutes": None}
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


def _name_the_judge(scratch: Path, host: Path | None) -> None:
    """eval-8ba65c4a: the agent may not change the scratch config, so the run names the judge:
    the host repository's when it has one (its provider decides which credential is read), else
    jev. Without a key the agent still sees "judging unavailable", naming the key."""
    from plumb.capture.configfile import update_section
    from plumb.config import load_config

    judgment = load_config(host).judgment if host else None
    if judgment is None or not judgment.backend:
        update_section(scratch, "judgment", {"backend": "jev"})
        return
    update_section(scratch, "judgment", {"backend": judgment.backend,
                                         "hook_timeout_ms": judgment.hook_timeout_ms,
                                         "jev": dict(judgment.jev)})


def scratch_repo(parent: Path, host: Path | None = None) -> Path:
    """A git repository with a first commit (so hooks work), adopted by plumb with the Claude
    Code hooks installed (the owner's choice, DEC-306) and a judge named from ``host``."""
    from plumb.commands import init_repo
    from plumb.hosts.claude_code import install

    root = Path(parent) / "scratch"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "eval@example.com")
    _git(root, "config", "user.name", "Eval")
    _git(root, "commit", "-q", "--allow-empty", "-m", "initial")
    init_repo(root)
    _name_the_judge(root, host)
    install.install(root)
    _hear_stand_in(root)
    return root


def _hear_stand_in(root: Path) -> None:
    """DEC-407: the scratch repository's hooks log the answers to the stand-in question tool
    as they log AskUserQuestion's (the plugin's hooks.json does the same, by matcher)."""
    from plumb.hosts.claude_code import install

    settings = install.read_settings(root)
    prefix = install.choose_launcher(root).hook_prefix
    settings.setdefault("hooks", {}).setdefault("PostToolUse", []).append({
        "matcher": ask_gate.STAND_IN_TOOL,
        "hooks": [{"type": "command", "command": f"{prefix} hook question-answer",
                   "async": True}]})
    (root / ".claude" / "settings.json").write_text(install._dump(settings), encoding="utf-8")


def claude_turn(binary: str, scratch: Path, message: str, *, model: str, session_id: str | None,
                system: str, timeout_s: float | None, env: dict[str, str] | None = None,
                max_turns: int | None = None, ask: dict[str, str] | None = None) -> dict[str, Any]:
    """One headless ``claude -p`` call in the scratch repository. ``ask`` (the owner's brief,
    the request in hand and the owner model) gives the agent the stand-in question tool that
    the scripted owner answers (DEC-407, SR-345)."""
    with tempfile.TemporaryDirectory(prefix="plumb-ask-") as folder:
        extra, tools, stand_in = _stand_in(Path(folder), ask)
        return _claude_call(binary, scratch, message, model=model, session_id=session_id,
                            system=system + stand_in, timeout_s=timeout_s, env=env,
                            max_turns=max_turns, extra=extra, tools=tools)


def _stand_in(folder: Path, ask: dict[str, str] | None) -> tuple[list[str], list[str], str]:
    """The ``claude`` arguments, the allowed tools and the system prompt line of the stand-in
    question tool, with its config files in ``folder`` (outside the scratch repository: the
    agent never reads the owner's brief)."""
    if not ask:
        return [], [], ""
    config = folder / "ask.json"
    config.write_text(json.dumps(ask, ensure_ascii=False), encoding="utf-8")
    plumb_src = str(Path(ask_server.__file__).resolve().parents[2])
    servers = folder / "mcp.json"
    servers.write_text(json.dumps({"mcpServers": {ask_gate.STAND_IN_SERVER: {
        "command": sys.executable, "args": ["-m", "plumb.evaluate.ask_server"],
        "env": {ask_server.CONFIG_ENV: str(config), "PYTHONPATH": plumb_src}}}}),
        encoding="utf-8")
    line = (f"\n\nTo ask the owner a question, call the {ask_gate.STAND_IN_TOOL} tool; the owner "
            "answers at once. Never write a question for the owner into your reply.")
    return ["--mcp-config", str(servers)], [ask_gate.STAND_IN_TOOL], line


def _claude_call(binary: str, scratch: Path, message: str, *, model: str, session_id: str | None,
                 system: str, timeout_s: float | None, env: dict[str, str] | None,
                 max_turns: int | None, extra: list[str], tools: list[str]) -> dict[str, Any]:
    argv = [binary, "-p", "--model", model, "--output-format", "json", *extra,
            *(["--max-turns", str(max_turns)] if max_turns else []),
            "--permission-mode", "acceptEdits",
            "--setting-sources", "project", "--append-system-prompt", system,
            *(["--resume", session_id] if session_id else []),
            "--allowedTools", *ALLOWED_TOOLS, *tools]
    # eval-52810e26: ``claude -p`` has no question tool; the launching session's
    # CLAUDE_CODE_SESSION_ATTENDED would make plumb's hooks send the agent after it
    env = {k: v for k, v in (os.environ if env is None else env).items()
           if k not in ("PLUMB_JOB", "PLUMB_WORKER", "CLAUDE_CODE_SESSION_ATTENDED")}
    # the agent's shell finds the plumb command of the interpreter running the benchmark
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if tools:   # plumb's hooks: a question tool is present although nobody attends (DEC-407)
        env[ask_gate.STAND_IN_ENV] = "1"
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
            "capped": maxed or bool(max_turns and int(data.get("num_turns") or 0) >= max_turns),
            "error": text[:300] if data.get("is_error") and not maxed else ""}


def _new_run_dir(parent: Path, name: str) -> Path:
    """A fresh run folder: two runs of one task and model in the same second get -2, -3, ..."""
    parent.mkdir(parents=True, exist_ok=True)
    for n in range(1, 10_000):
        run_dir = parent / (name if n == 1 else f"{name}-{n}")
        try:
            run_dir.mkdir()
            return run_dir
        except FileExistsError:
            continue
    raise RuntimeError(f"no free run folder for {name} in {parent}")


def run_task(root: Path, task: Any, *, model: str, owner: Any, runs_dir: Path | None = None,
             claude=claude_turn, now=time.monotonic, binary: str | None = None,
             limits: dict[str, int | None] | None = None) -> RunResult:
    binary = binary or shutil.which("claude")
    if binary is None:   # raised before any folder is made (SR-344 EX-3)
        raise RuntimeError("the claude command was not found on this machine")
    limits = {**NO_LIMITS, **(limits or {})}
    run_cap_s = limits["minutes"] * 60 if limits["minutes"] else None
    root = Path(root)
    run_dir = _new_run_dir(runs_dir or root / ".plumb" / "eval" / "runs",
                           f"{time.strftime('%Y%m%dT%H%M%S')}-{task.name}-{model}")
    scratch = scratch_repo(Path(tempfile.mkdtemp(prefix="plumb-eval-")), host=root)
    transcript: list[Turn] = []
    state: dict[str, Any] = {"session": None, "start": now(), "out_of_time": False}

    def send(n: int, message: str, source: str) -> Turn:
        transcript.append(Turn("owner", message, n, source))
        left = None if run_cap_s is None else run_cap_s - (now() - state["start"])
        if left is not None and left <= 0:
            state["out_of_time"] = True
            turn = Turn("agent", "", n, "capped")
        else:
            got = claude(binary, scratch, message, model=model, session_id=state["session"],
                         system=task.agent_brief, timeout_s=left, env=None,
                         max_turns=limits["turns"],
                         ask={"brief": task.owner_brief, "request": task.requests[n - 1],
                              "owner_model": str(getattr(owner, "model", "haiku"))})
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
            if limits["exchanges"] is not None and sent >= limits["exchanges"]:
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
