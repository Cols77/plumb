"""Drive plumb's installed Claude Code hooks the way Claude Code would (plan 4.5).

Reads the hook and status-line commands that ``plumb hooks install`` wrote into
``<root>/.claude/settings.json``, expands ``$CLAUDE_PROJECT_DIR``, and runs each one as its
own process with the JSON payload Claude Code sends on stdin and the settings' ``env``
(the session marker). Each step records its stdout and wall time.

The session it simulates:

1. ``SessionStart`` (the brief);
2. ``UserPromptSubmit`` with a prompt that contradicts a confirmed requirement (the
   intent-change flag), then ``Stop`` with nothing changed;
3. ``UserPromptSubmit`` with a prompt that names a requirement (records, examples, tests);
4. the agent edits a source file, then ``PostToolUse`` for ``Edit``;
5. ``Stop``: blocks once, asking for the covering tests;
6. the agent runs the test command the block names (the turn's covering tests);
7. ``Stop`` with ``stop_hook_active``: the end-of-turn alignment summary;
8. the status line.

Usage: ``python scripts/drive_session.py --root . --edit src/plumb/text.py
--prompt-change "..." --prompt "..." [--json]``. The edit appends one comment line and
``--restore`` puts the file back afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

HOOK_LIMIT_S = 2.0
EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop")


@dataclass
class Step:
    name: str
    ms: float
    code: int
    stdout: str
    stderr: str


def _argv(command: str, root: Path) -> list[str]:
    command = command.replace("$CLAUDE_PROJECT_DIR", root.as_posix())
    argv = shlex.split(command, posix=True)
    if argv and not Path(argv[0]).is_absolute():
        found = shutil.which(argv[0])
        if found:
            argv[0] = found
    return argv


def installed_commands(root: Path) -> tuple[dict[str, list[str]], list[str], dict[str, str]]:
    """``(hook argv per event, status-line argv, env)`` from ``.claude/settings.json``."""
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks: dict[str, list[str]] = {}
    for event in EVENTS:
        for group in settings.get("hooks", {}).get(event, []):
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                if "plumb" in command and " hook " in command:
                    hooks[event] = _argv(command, root)
    status = _argv(settings["statusLine"]["command"], root)
    env = {k: str(v) for k, v in (settings.get("env") or {}).items()}
    return hooks, status, env


def _run(name: str, argv: list[str], root: Path, env: dict[str, str],
         payload: dict | None, timeout: float = 120.0) -> Step:
    full_env = {**os.environ, **env, "CLAUDE_PROJECT_DIR": str(root),
                "PYTHONIOENCODING": "utf-8"}
    stdin = json.dumps(payload) if payload is not None else ""
    start = time.perf_counter()
    result = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=root, env=full_env,
                            timeout=timeout)
    ms = (time.perf_counter() - start) * 1000
    return Step(name, round(ms, 1), result.returncode, result.stdout, result.stderr)


def tests_command(stop_stdout: str) -> list[str]:
    """The ``plumb tests run ...`` arguments a Stop block asks for (after ``plumb``)."""
    try:
        reason = json.loads(stop_stdout).get("reason", "")
    except ValueError:
        reason = ""
    marker = "run 'plumb "
    if marker not in reason:
        return ["tests", "run", "--changed"]
    command = reason.split(marker, 1)[1].split("' (", 1)[0]
    return shlex.split(command, posix=True)


def drive(root: Path, *, edit: str, prompt_change: str, prompt: str,
          session_id: str = "plumb-driven-1", restore: bool = False) -> list[Step]:
    """Run the simulated session against ``root``; returns every step in order."""
    root = Path(root).resolve()
    hooks, status_argv, env = installed_commands(root)
    missing = [e for e in EVENTS if e not in hooks]
    if missing:
        raise SystemExit(f"plumb hooks not installed for: {', '.join(missing)}")
    base = {"session_id": session_id, "transcript_path": "", "cwd": str(root)}
    steps: list[Step] = []

    def hook(name: str, event: str, **fields: object) -> Step:
        step = _run(name, hooks[event], root, env, {**base, "hook_event_name": event, **fields})
        steps.append(step)
        return step

    hook("SessionStart", "SessionStart", source="startup")
    hook("UserPromptSubmit (contradicts)", "UserPromptSubmit", prompt=prompt_change)
    hook("Stop (no change)", "Stop", stop_hook_active=False)
    hook("UserPromptSubmit (names SR)", "UserPromptSubmit", prompt=prompt)

    target = root / edit
    original = target.read_bytes()
    try:
        time.sleep(0.05)  # the edit's mtime must follow the turn start
        target.write_bytes(original + b"# edited by the driven session\n")
        hook("PostToolUse Edit", "PostToolUse", tool_name="Edit",
             tool_input={"file_path": str(target), "old_string": "",
                         "new_string": "# edited by the driven session\n"},
             tool_response={"filePath": str(target), "success": True})
        stop = hook("Stop", "Stop", stop_hook_active=False)
        # the agent runs the test command the block names, in its own turn, with the hook's
        # interpreter
        prefix = hooks["Stop"][: hooks["Stop"].index("hook")]
        steps.append(_run("covering tests", [*prefix, *tests_command(stop.stdout)], root, env,
                          None, timeout=600))
        hook("Stop (stop_hook_active)", "Stop", stop_hook_active=True)
    finally:
        if restore:
            target.write_bytes(original)
    steps.append(_run("statusline", status_argv, root, env,
                      {**base, "hook_event_name": "Status"}))
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--edit", required=True, help="repository-relative source file")
    parser.add_argument("--prompt-change", required=True,
                        help="a prompt contradicting a confirmed requirement")
    parser.add_argument("--prompt", required=True, help="a prompt naming a requirement")
    parser.add_argument("--restore", action="store_true", help="undo the edit afterwards")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    steps = drive(Path(args.root), edit=args.edit, prompt_change=args.prompt_change,
                  prompt=args.prompt, restore=args.restore)
    if args.json:
        print(json.dumps([asdict(s) for s in steps], indent=2))
        return 0
    for step in steps:
        print(f"=== {step.name}: {step.ms:.0f} ms (exit {step.code})")
        if step.stdout.strip():
            print(step.stdout.rstrip())
        if step.stderr.strip():
            print("stderr: " + step.stderr.rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
