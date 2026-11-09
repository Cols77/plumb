"""Drive iaso's installed Claude Code hooks the way Claude Code would (plan 4.5).

Reads the hook and status-line commands that ``iaso hooks install`` wrote into
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

Usage: ``python scripts/drive_session.py --root . --edit src/iaso/text.py
--prompt-change "..." --prompt "..." [--json]``. The edit appends one comment line and
``--restore`` puts the file back afterwards.

``--capture`` drives the capture flow instead (``drive_capture``): the owner's new intent,
``iaso capture`` (an INT read-back, an SR with proposed examples, a DEC that matters), the
decision asked once, the read-back shown as an intent card, and the owner's "ok" answered: the
prompt hook queues the reading of it and tells the agent to confirm nothing. It writes
proposed records, so run it on a scratch copy.
``--merge-check BASE`` runs ``iaso merge-check BASE --no-run --json`` (never the full run).
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
                # PostToolUse holds two commands since STALE (the edit tracker, then the
                # synchronous edit check); this driver runs the tracker
                if command.rstrip().endswith(" edit-check"):
                    continue
                if "iaso" in command and " hook " in command:
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
    """The ``iaso tests run ...`` arguments a Stop block asks for (after ``iaso``)."""
    try:
        reason = json.loads(stop_stdout).get("reason", "")
    except ValueError:
        reason = ""
    marker = "run 'iaso "
    if marker not in reason:
        return ["tests", "run", "--changed"]
    command = reason.split(marker, 1)[1].split("' (", 1)[0]
    return shlex.split(command, posix=True)


def drive(root: Path, *, edit: str, prompt_change: str, prompt: str,
          session_id: str = "iaso-driven-1", restore: bool = False) -> list[Step]:
    """Run the simulated session against ``root``; returns every step in order."""
    root = Path(root).resolve()
    hooks, status_argv, env = installed_commands(root)
    missing = [e for e in EVENTS if e not in hooks]
    if missing:
        raise SystemExit(f"iaso hooks not installed for: {', '.join(missing)}")
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
        # the edit made a link stale and the turn is held until the agent resolves it (SR-111);
        # the driven edit only appends a comment, so the agent repins what it made stale
        steps.append(_run("repin", [*prefix, "repin", "--all-stale", "--note",
                                    "the driven edit only appended a comment"], root, env, None))
        hook("Stop (stop_hook_active)", "Stop", stop_hook_active=True)
    finally:
        if restore:
            target.write_bytes(original)
    steps.append(_run("statusline", status_argv, root, env,
                      {**base, "hook_event_name": "Status"}))
    return steps


CAPTURE_PROMPT = ("Add a subtract helper next to add; 5 minus 3 is 2. Negative results are "
                  "fine.")
CAPTURE_DOC: dict = {
    "intent": {"quote": "Add a subtract helper next to add",
               "readback": "Add sub(a, b) beside add, returning a - b",
               "will": ["sub(a, b) returns a - b"], "wont": ["no change to add or mul"],
               "assumptions": ["integers, like add"]},
    "requirements": [{"title": "sub returns the difference of two numbers",
                      "statement": "pkg.mod.sub(a, b) returns the difference a - b.",
                      "examples": [{"given": "the numbers 5 and 3", "when": "sub is called",
                                    "then": "it returns 2", "quote": "5 minus 3 is 2"},
                                   {"given": "the numbers 3 and 5", "when": "sub is called",
                                    "then": "it returns -2"}],
                      "implemented_by": ["src/pkg/mod.py"]}],
    "decisions": [{"question": "Floats too, or integers only?", "chosen": "integers only",
                   "alternatives": ["floats too"], "matters": True,
                   "recommended": "integers only", "decides": ["#1"]}],
}


def drive_capture(root: Path, *, prompt: str = CAPTURE_PROMPT, doc: dict | None = None,
                  affirm: str = "ok", session_id: str = "iaso-driven-capture") -> list[Step]:
    """The capture flow through the installed hooks (sp2, R1, R2, R11):

    1. ``SessionStart``, then the owner's new intent (``UserPromptSubmit``, logged by the
       prompt hook);
    2. the agent records the read-back in one call (``iaso capture --prompt <digest>``):
       an INT, an SR with a proposed example, a DEC that matters, all proposed;
    3. ``Stop``: the decision that matters is asked (one per message);
    4. ``Stop`` with ``stop_hook_active``: the end-of-turn summary shows the read-back as an
       intent card with its proposed examples;
    5. ``Stop`` again in the same turn: the decision is not asked a second time;
    6. the owner answers ``affirm`` (``UserPromptSubmit``): the prompt hook tells the agent
       to confirm nothing (no relay line); iaso reads the answer itself;
    7. the status line.
    """
    import hashlib

    root = Path(root).resolve()
    hooks, status_argv, env = installed_commands(root)
    missing = [e for e in EVENTS if e not in hooks]
    if missing:
        raise SystemExit(f"iaso hooks not installed for: {', '.join(missing)}")
    base = {"session_id": session_id, "transcript_path": "", "cwd": str(root)}
    prefix = hooks["Stop"][: hooks["Stop"].index("hook")]
    steps: list[Step] = []

    def hook(name: str, event: str, **fields: object) -> Step:
        step = _run(name, hooks[event], root, env, {**base, "hook_event_name": event, **fields})
        steps.append(step)
        return step

    def iaso(name: str, *args: str) -> Step:
        step = _run(name, [*prefix, *args], root, env, None)
        steps.append(step)
        return step

    hook("SessionStart (capture)", "SessionStart", source="startup")
    hook("UserPromptSubmit (new intent)", "UserPromptSubmit", prompt=prompt)
    digest = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    doc_path = root / ".iaso" / "session" / session_id / "capture.json"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(json.dumps(CAPTURE_DOC if doc is None else doc), encoding="utf-8")
    iaso("iaso capture", "capture", "--prompt", digest, "--file", str(doc_path))
    hook("Stop (asks the decision)", "Stop", stop_hook_active=False)
    hook("Stop (read-back shown)", "Stop", stop_hook_active=True)
    hook("Stop (not asked again)", "Stop", stop_hook_active=False)
    hook("Stop (summary again)", "Stop", stop_hook_active=True)
    hook("UserPromptSubmit (owner ok)", "UserPromptSubmit", prompt=affirm)
    steps.append(_run("statusline", status_argv, root, env,
                      {**base, "hook_event_name": "Status"}))
    return steps


def merge_check(root: Path, base: str = "main") -> Step:
    """``iaso merge-check BASE --no-run --json`` on ``root``: the merge boundary report,
    without the full run (that belongs to the Integrate phase alone)."""
    root = Path(root).resolve()
    hooks, _, env = installed_commands(root)
    prefix = hooks["Stop"][: hooks["Stop"].index("hook")]
    return _run("merge-check", [*prefix, "merge-check", base, "--no-run", "--json"], root,
                env, None, timeout=600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--edit", help="repository-relative source file")
    parser.add_argument("--prompt-change",
                        help="a prompt contradicting a confirmed requirement")
    parser.add_argument("--prompt", help="a prompt naming a requirement")
    parser.add_argument("--restore", action="store_true", help="undo the edit afterwards")
    parser.add_argument("--capture", action="store_true",
                        help="drive the capture flow instead (writes proposed records and "
                             "answers the owner's 'ok': use a scratch copy)")
    parser.add_argument("--merge-check", metavar="BASE", default=None,
                        help="also run iaso merge-check BASE --no-run --json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.capture:
        steps = drive_capture(Path(args.root))
    elif args.edit and args.prompt_change and args.prompt:
        steps = drive(Path(args.root), edit=args.edit, prompt_change=args.prompt_change,
                      prompt=args.prompt, restore=args.restore)
    elif args.merge_check:
        steps = []
    else:
        parser.error("--edit, --prompt-change and --prompt are required without --capture")
    if args.merge_check:
        steps.append(merge_check(Path(args.root), args.merge_check))
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
