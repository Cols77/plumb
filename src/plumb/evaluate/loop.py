"""SR-348: evaluate, debug, merge, evaluate again; stops at the owner's decisions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def merge_branch(root: Path, branch: str) -> str:
    """Merge through the repository's hooks (never --no-verify); "" or what holds it."""
    git = ["git", "-C", str(root)]
    done = subprocess.run([*git, "merge", "--no-ff", "--no-edit", "-m",
                           f"Merge {branch}: evaluate fix", branch],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode == 0:
        return ""
    subprocess.run([*git, "merge", "--abort"], capture_output=True)
    lines = [ln for ln in (done.stderr or done.stdout).splitlines() if ln.strip()]
    return lines[-1].strip() if lines else f"git merge exited {done.returncode}"


def run_loop(root: Path, task: Any, *, model: str, rounds: int, run: Any = None,
             fix: Any = None, merge: Any = merge_branch, **run_kw: Any) -> int:
    from plumb import debug, selfdebug
    from plumb.api import open_core
    from plumb.evaluate import issues
    from plumb.evaluate import run as runmod

    run, fix = run or runmod.run_task, fix or selfdebug.fix
    for n in range(1, rounds + 1):
        print(f"round {n}")
        result = run(root, task, model=model, **run_kw)
        if not result.issues:
            print("stopped: the run filed no issue")
            return 0
        ids = issues.open_cases(root, result.issues)
        print(f"cases opened: {len(ids)}")
        cases = {c["id"]: c for c in debug.all_cases(root)}
        for case_id in ids:
            out = fix(open_core(Path(root)), cases.get(case_id, {"id": case_id}))
            print(f"  {case_id}: {out.state}: {out.detail}")
            if out.state in ("owner", "held"):
                print(f"stopped: {case_id} waits for the owner ({out.detail})")
                return 1
            if out.state == "fixed":
                held = merge(root, out.branch)
                if held:
                    print(f"stopped: the merge of {out.branch} is held: {held}")
                    return 1
                print(f"  merged {out.branch}")
    print("stopped: rounds done")
    return 0
