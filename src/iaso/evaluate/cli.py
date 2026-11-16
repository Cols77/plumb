"""SR-344, SR-348: ``iaso evaluate <task> (--no-limits | --max-exchanges N --max-turns N
--max-minutes N) [--model M] [--owner-model M] [--rounds N] [--runs-dir D]``."""

from __future__ import annotations

from pathlib import Path


def _proof(command: str, argv: list[str]) -> int:
    """SR-397: ``iaso evaluate proof SR-### [SR-### ...]``, one evaluator per proof."""
    import argparse

    from iaso.api import open_core
    from iaso.capture.records import CaptureError
    from iaso.cliutil import resolve_root
    from iaso.evaluate import proofcheck

    parser = argparse.ArgumentParser(
        prog=f"iaso {command} proof",
        description="Run the independent evaluator on the proofs the owner picked it for.")
    parser.add_argument("ids", nargs="+", metavar="SR-###")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-minutes", type=int, default=30, metavar="N")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    try:
        rows = proofcheck.evaluate_proofs(open_core(resolve_root(args.root)), args.ids,
                                          model=args.model, minutes=args.max_minutes)
    except (ValueError, CaptureError) as exc:
        print(f"iaso: evaluate proof: {exc}")
        return 2
    print("\n".join(proofcheck.lines(rows)))
    return 0 if all(r["verdict"] == "verified" for r in rows) else 1


def _case(command: str, argv: list[str]) -> int:
    """SR-397 EX-8: ``iaso evaluate case <folder>``: an evaluator's case, no fix rounds."""
    import argparse

    from iaso.cliutil import resolve_root
    from iaso.evaluate import owner, tasks
    from iaso.evaluate import run as runmod

    parser = argparse.ArgumentParser(prog=f"iaso {command} case",
                                     description="Run an evaluation case folder.")
    parser.add_argument("folder")
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--owner-model", default="haiku")
    parser.add_argument("--max-minutes", type=int, default=20, metavar="N")
    parser.add_argument("--max-turns", type=int, metavar="N")
    parser.add_argument("--max-exchanges", type=int, metavar="N")
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    try:
        task = tasks.load_case(args.folder)
    except (OSError, ValueError) as exc:
        print(f"iaso: evaluate case: {exc}")
        return 2
    runmod.run_task(resolve_root(args.root), task, model=args.model,
                    owner=owner.ScriptedOwner(args.owner_model),
                    runs_dir=Path(args.runs_dir) if args.runs_dir else None,
                    limits={"exchanges": args.max_exchanges, "turns": args.max_turns,
                            "minutes": args.max_minutes})
    return 0


def run(command: str, argv: list[str]) -> int:
    import argparse

    from iaso.cliutil import resolve_root
    from iaso.evaluate import loop, owner, proofcheck, tasks
    from iaso.evaluate import run as runmod

    if argv[:1] == ["proof"]:
        return _proof(command, argv[1:])
    if argv[:1] == ["case"]:
        return _case(command, argv[1:])

    parser = argparse.ArgumentParser(
        prog=f"iaso {command}",
        description="Benchmark: a cheap model works through a task with iaso; prints the score.")
    parser.add_argument("task", choices=tasks.NAMES)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--owner-model", default="haiku")
    parser.add_argument("--rounds", type=int, default=1, metavar="N",
                        help="fix rounds after a run: the issues become debug cases, the debug "
                             "workflow fixes them, the fixes merge, the task runs again "
                             "(default 1; 0 only documents the issues)")
    parser.add_argument("--max-exchanges", type=int, metavar="N",
                        help="owner answers per request; beyond it a question counts unanswered")
    parser.add_argument("--max-turns", type=int, metavar="N", help="agent turns per request")
    parser.add_argument("--max-minutes", type=int, metavar="N", help="minutes per run")
    parser.add_argument("--no-limits", action="store_true", help="run without any limit")
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--proof-evaluator", action="store_true",
                        help="the owner picked the independent evaluator for this run's fixes "
                             "at launch")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    named = {"exchanges": args.max_exchanges, "turns": args.max_turns,
             "minutes": args.max_minutes}
    if not args.no_limits and all(v is None for v in named.values()):
        # the owner chooses: the agent asks with the question tool, never picks for them
        print("iaso: evaluate: the run's limits are the owner's choice; ask them with the "
              "question tool, then pass --max-exchanges N --max-turns N --max-minutes N "
              "(any of them) or --no-limits")
        return 2
    from iaso.hosts.claude_code import claude_binary

    binary = claude_binary()
    if binary is None:
        print("iaso: evaluate: the claude command was not found on this machine")
        return 1
    root = resolve_root(args.root)
    kw = {"model": args.model, "binary": binary,
          "owner": owner.ScriptedOwner(args.owner_model),
          "runs_dir": Path(args.runs_dir) if args.runs_dir else None, "limits": named}
    task = tasks.load(args.task)
    if args.rounds > 0:   # DEC-309: the loop runs by itself; each fix round ends in a rerun
        check = proofcheck.check_fix if args.proof_evaluator else None
        return loop.run_loop(root, task, rounds=args.rounds + 1, check=check, **kw)
    name = loop.start(root, task, args.model, 0)
    try:
        runmod.run_task(root, task, **kw)
    finally:
        loop.note(root, name, ended=True)
    return 0
