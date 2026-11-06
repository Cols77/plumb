"""SR-348: evaluate, debug, merge, evaluate again; stops at the owner's decisions."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

STORE = (".plumb", "cache", "evaluate")


def _stale_links(root: Path) -> set[str]:
    """The stale file links of the repository's records (none when it holds no records)."""
    from plumb.api import open_core

    try:
        return {st.link.id for st in open_core(Path(root)).link_states()
                if st.state == "stale" and st.link.target.path}
    except Exception:  # noqa: BLE001 - a repository without records has no links to repin
        return set()


def _repin(root: Path, link: str) -> str:
    """``plumb repin --after-tests``: "" once repinned, else why it was refused."""
    import sys

    done = subprocess.run([sys.executable, "-m", "plumb", "repin", "--after-tests", link],
                          cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    out = (done.stdout + done.stderr).strip().splitlines()
    return "" if done.returncode == 0 else (out[-1] if out else f"repin of {link} refused")


def merge_branch(root: Path, branch: str, *, repin: Any = None) -> str:
    """Merge through the repository's hooks (never --no-verify); "" or what holds it. The
    links the fix moved are repinned after their tests pass and the meaning is kept, and the
    issues file goes into the merge, before the hooks check it."""
    from plumb.evaluate.issues import ACCUMULATED

    repin = repin or _repin
    git = ["git", "-C", str(root)]
    run = lambda *a: subprocess.run([*git, *a], capture_output=True, text=True,  # noqa: E731
                                    encoding="utf-8", errors="replace")
    # the merge carries the requirement lines of the fix's own commits (the hook asks for one)
    body = run("log", "--format=%B", f"HEAD..{branch}").stdout
    srs = sorted({s.strip() for line in body.splitlines() if line.startswith("SR:")
                  for s in line[3:].split(",") if s.strip()} or {"SR-348"})
    before = _stale_links(root)
    done = run("merge", "--no-ff", "--no-commit", branch)
    if done.returncode == 0:
        for link in sorted(_stale_links(root) - before):
            if why := repin(root, link):
                run("merge", "--abort")
                return f"{link} could not be repinned: {why}"
        kept = [p for p in (".plumb/requirements", ".plumb/decisions", ".plumb/intents",
                            "/".join(ACCUMULATED)) if (Path(root) / p).exists()]
        if kept:   # git add refuses the whole call on a path that does not exist
            run("add", "--", *kept)
        done = run("commit", "-m", f"Merge {branch}: evaluate fix\n\nSR: {', '.join(srs)}")
        if done.returncode == 0:
            return ""
    run("merge", "--abort")
    lines = [ln for ln in (done.stderr or done.stdout).splitlines() if ln.strip()]
    return lines[-1].strip() if lines else f"git merge exited {done.returncode}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def note(root: Path, name: str, **fields: Any) -> None:
    """SR-392: what the loop list shows of a run; one small file per run, never raises."""
    from plumb.understand import loops

    path = Path(root).joinpath(*STORE, f"{name}.json")
    try:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**data, **fields, "updated_at": _now()}), "utf-8")
    except OSError:
        pass
    loops.touch(root)


def start(root: Path, task: Any, model: str, rounds: int) -> str:
    """Note a new run (``rounds`` fix rounds asked); returns its name."""
    name = f"{_now().replace('-', '').replace(':', '')}-{getattr(task, 'name', '')}-{model}"
    note(root, name, task=getattr(task, "name", ""), model=model, rounds=rounds, iteration=1,
         stage="run", filed=0, pid=os.getpid(), started_at=_now())
    return name


def _words(n: int, rounds: int, stage: str) -> tuple[str, list[str]]:
    """Where iteration ``n`` stands (each of the rounds + 1 iterations runs, then fixes) and
    what is left."""
    more = rounds - n
    after = [f"{more} more fix round" + "s" * (more > 1)] * (more > 0)
    if stage == "run":
        return (("first run" if n == 1 else f"rerun after round {n - 1} of {rounds}"),
                ["the fix round", "the rerun", *after] if n <= rounds
                else ["the fixes of the last run"] * bool(rounds))
    if n > rounds:
        return "fixing what the last run found", ["the fixes of the last run"]
    if stage == "fix":
        return f"round {n} of {rounds}", ["the fix round", "the rerun", *after]
    return "merging the fix", ["the rerun", *after]


def rows(root: Path) -> list[dict[str, Any]]:
    """SR-392: the evaluate runs not ended, for the loop list; a stopped one says why."""
    from plumb.progress import _alive

    out = []
    for path in sorted(Path(root).joinpath(*STORE).glob("*.json")):
        try:
            d = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("ended"):
            continue
        stopped = str(d.get("stopped") or "")
        words, left = _words(int(d.get("iteration") or 1), int(d.get("rounds") or 0),
                             str(d.get("stage") or "run"))
        filed = int(d.get("filed") or 0)
        live = not stopped and _alive(d.get("pid"))
        last = str(d.get("updated_at") or "")
        goal = f"how {d.get('model')} does the {d.get('task')} task with plumb, and what plumb gets wrong"
        out.append({
            "kind": "evaluate", "id": path.stem, "intent": "", "goal": goal, "goal_full": goal,
            "progress": f"{d.get('task')} · {d.get('model')} · {'stopped' if stopped else words}"
                        + (f" · {filed} problem{'s' * (filed != 1)} filed" if filed else ""),
            "done": [], "left": left, "waits": f"stopped: {stopped}" if stopped else "",
            "live": live, "state": "running" if live else "idle", "last": last,
            "idle_since": "" if live else last[:10], "branch": "", "root": str(root),
            "session": "", "reopen": False, "send": False, "message": None})
    return out


def run_loop(root: Path, task: Any, *, model: str, rounds: int, run: Any = None,
             fix: Any = None, merge: Any = merge_branch, **run_kw: Any) -> int:
    from plumb import debug, selfdebug
    from plumb.api import open_core
    from plumb.evaluate import issues
    from plumb.evaluate import run as runmod

    run, fix = run or runmod.run_task, fix or selfdebug.fix
    name, filed = start(root, task, model, rounds - 1), 0
    stop = lambda why, code, **kw: (note(root, name, stopped=why, **kw), code)[1]  # noqa: E731
    issues.open_cases(root, issues.accumulated(root))   # earlier runs' issues are fixed too
    for n in range(1, rounds + 1):
        print(f"round {n}")
        note(root, name, iteration=n, stage="run")
        result = run(root, task, model=model, **run_kw)
        if result.score.get("errors"):   # a run whose agent turns failed says nothing of plumb
            print(f"stopped: {result.score['errors']} agent turns failed: {result.score['error']}")
            return stop(f"{result.score['errors']} agent turns failed", 1)
        ids = issues.open_cases(root, result.issues)
        filed += len(ids)
        note(root, name, filed=filed)
        cases = {c["id"]: c for c in debug.all_cases(root)}
        todo = list(dict.fromkeys([*ids, *(i for i, c in cases.items() if c.get("kind")
                                           == "eval-issue" and c.get("state") == "open"
                                           and not c.get("report"))]))
        if not todo:
            print("stopped: the run filed no issue and no earlier issue waits")
            note(root, name, ended=True)
            return 0
        print(f"cases opened: {len(ids)}, to fix: {len(todo)}")
        for case_id in todo:
            # plumb's background self-debug may have taken the case meanwhile (SR-343)
            now = {c["id"]: c for c in debug.all_cases(root)}
            if case_id in now and now[case_id].get("state") != "open":
                print(f"  {case_id}: already settled elsewhere")
                continue
            note(root, name, stage="fix")
            try:
                out = fix(open_core(Path(root)), cases.get(case_id, {"id": case_id}))
            except Exception as exc:  # noqa: BLE001 - one case's crash must not end the loop
                print(f"  {case_id}: error: {type(exc).__name__}: {exc}")
                continue
            print(f"  {case_id}: {out.state}: {out.detail}")
            if out.state in ("owner", "held"):
                print(f"stopped: {case_id} waits for the owner ({out.detail})")
                return stop(f"{case_id} waits for the owner ({out.detail})", 1)
            if out.state == "fixed":
                note(root, name, stage="merge")
                held = merge(root, out.branch)
                if held:
                    print(f"stopped: the merge of {out.branch} is held: {held}")
                    return stop(f"the merge of {out.branch} is held: {held}", 1)
                print(f"  merged {out.branch}")
    print("stopped: rounds done")
    note(root, name, ended=True)
    return 0
