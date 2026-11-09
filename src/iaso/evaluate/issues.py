"""SR-347, SR-348: the issues a cheap agent files while it works, kept per run and accumulated
in iaso's repository, and opened as debug cases so the debug round can fix them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ISSUES_FILE = ".iaso/eval-issues.jsonl"        # in the scratch repository, written by the agent
ACCUMULATED = (".iaso", "eval", "issues.jsonl")  # in iaso's repository, tracked


def collect(scratch: Path, run_dir: Path, root: Path, run_id: str, task: str,
            model: str) -> list[dict[str, Any]]:
    """The agent's issue lines (bad lines skipped), kept in the run folder and accumulated."""
    try:
        text = (Path(scratch) / ISSUES_FILE).read_text(encoding="utf-8")
    except OSError:
        text = ""
    found: list[dict[str, Any]] = []
    for raw in text.splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            found.append(row)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "issues.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in found), encoding="utf-8")
    if found:
        target = Path(root).joinpath(*ACCUMULATED)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            for row in found:
                handle.write(json.dumps({**row, "run": run_id, "task": task, "model": model},
                                        ensure_ascii=False) + "\n")
    return found


def case_id(issue: dict[str, Any]) -> str:
    key = f"{issue.get('command', '')}\n{issue.get('got', '')}"
    return "eval-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def open_cases(root: Path, issues: list[dict[str, Any]]) -> list[str]:
    """Open one debug case per distinct issue; returns the ids that were not open before."""
    from iaso import debug

    opened: list[str] = []
    for issue in issues:
        cid = case_id(issue)
        if debug._case_path(root, cid).exists() or cid in opened:
            continue
        detail = f"expected: {issue.get('expected', '')}; got: {issue.get('got', '')}"
        debug.open_case(root, id=cid, kind="eval-issue", target=str(issue.get("command", "")),
                        detail=detail, log=str(issue.get("context", "")))
        opened.append(cid)
    return opened


def accumulated(root: Path) -> list[dict[str, Any]]:
    """Every issue kept in iaso's repository so far (bad lines skipped)."""
    try:
        text = Path(root).joinpath(*ACCUMULATED).read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for raw in text.splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("command"):
            rows.append(row)
    return rows
