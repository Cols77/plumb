"""SR-348: evaluate, debug, merge, evaluate again; stops at the owner's decisions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def merge_branch(root: Path, branch: str) -> str:
    """Merge through the repository's hooks (never --no-verify); "" or what holds it."""
    git = ["git", "-C", str(root)]
    # the merge carries the requirement lines of the fix's own commits (the hook asks for one)
    body = subprocess.run([*git, "log", "--format=%B", f"HEAD..{branch}"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout
    srs = sorted({s.strip() for line in body.splitlines() if line.startswith("SR:")
                  for s in line[3:].split(",") if s.strip()} or {"SR-348"})
    done = subprocess.run([*git, "merge", "--no-ff", "--no-edit", "-m",
                           f"Merge {branch}: evaluate fix\n\nSR: {', '.join(srs)}", branch],
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
    issues.open_cases(root, issues.accumulated(root))   # earlier runs' issues are fixed too
    for n in range(1, rounds + 1):
        print(f"round {n}")
        result = run(root, task, model=model, **run_kw)
        if result.score.get("errors"):   # a run whose agent turns failed says nothing of plumb
            print(f"stopped: {result.score['errors']} agent turns failed: {result.score['error']}")
            return 1
        ids = issues.open_cases(root, result.issues)
        cases = {c["id"]: c for c in debug.all_cases(root)}
        todo = list(dict.fromkeys([*ids, *(i for i, c in cases.items() if c.get("kind")
                                           == "eval-issue" and c.get("state") == "open"
                                           and not c.get("report"))]))
        if not todo:
            print("stopped: the run filed no issue and no earlier issue waits")
            return 0
        print(f"cases opened: {len(ids)}, to fix: {len(todo)}")
        for case_id in todo:
            # plumb's background self-debug may have taken the case meanwhile (SR-343)
            now = {c["id"]: c for c in debug.all_cases(root)}
            if case_id in now and now[case_id].get("state") != "open":
                print(f"  {case_id}: already settled elsewhere")
                continue
            try:
                out = fix(open_core(Path(root)), cases.get(case_id, {"id": case_id}))
            except Exception as exc:  # noqa: BLE001 - one case's crash must not end the loop
                print(f"  {case_id}: error: {type(exc).__name__}: {exc}")
                continue
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
