"""SR-344, SR-348: ``plumb evaluate <task> [--model M] [--owner-model M] [--loop N]
[--runs-dir D]``."""

from __future__ import annotations

import shutil
from pathlib import Path


def run(command: str, argv: list[str]) -> int:
    import argparse

    from plumb.cliutil import resolve_root
    from plumb.evaluate import loop, owner, tasks
    from plumb.evaluate import run as runmod

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Benchmark: a cheap model works through a task with plumb; prints the score.")
    parser.add_argument("task", choices=tasks.NAMES)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--owner-model", default="haiku")
    parser.add_argument("--loop", type=int, default=0, metavar="N",
                        help="evaluate, debug, merge, evaluate again, up to N rounds")
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    binary = shutil.which("claude")
    if binary is None:
        print("plumb: evaluate: the claude command was not found on this machine")
        return 1
    root = resolve_root(args.root)
    kw = {"model": args.model, "binary": binary,
          "owner": owner.ScriptedOwner(args.owner_model),
          "runs_dir": Path(args.runs_dir) if args.runs_dir else None}
    task = tasks.load(args.task)
    if args.loop:
        return loop.run_loop(root, task, rounds=args.loop, **kw)
    runmod.run_task(root, task, **kw)
    return 0
