"""SR-346: the score of one run: the task's checks passed, and what iaso's trail shows."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

RECORD_DIRS = ("intents", "requirements", "decisions")
CHECKS_TIMEOUT_S = 300


def checks(scratch: Path, task: Any, python: str = sys.executable) -> dict[str, Any]:
    """Run the task's checks against the scratch repository's code."""
    scratch = Path(scratch)
    files = list(Path(task.checks).glob("test_*.py")) if Path(task.checks).is_dir() else []
    if not files:
        return {"checks_passed": 0, "checks_total": 0, "failed": []}
    target = scratch / "eval_checks"
    shutil.copytree(task.checks, target, dirs_exist_ok=True)
    out = ""
    try:
        done = subprocess.run([python, "-m", "pytest", "eval_checks", "-q", "-rf",
                               "-p", "no:cacheprovider"], cwd=scratch, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=CHECKS_TIMEOUT_S)
        out = done.stdout
    except subprocess.TimeoutExpired:
        pass
    finally:
        shutil.rmtree(target, ignore_errors=True)
    count = {w: int(m.group(1)) if (m := re.search(rf"(\d+) {w}", out)) else 0
             for w in ("passed", "failed", "error")}
    failed = re.findall(r"^FAILED \S+?::(\S+)", out, re.MULTILINE)
    total = count["passed"] + count["failed"] + count["error"]
    if total == 0:   # nothing collected or timed out: every check of the task counts as missed
        total = sum(len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), re.MULTILINE))
                    for f in files)
    return {"checks_passed": count["passed"], "checks_total": total, "failed": failed}


def trail(scratch: Path, transcript: list[Any], issues: list[dict[str, Any]],
          unanswered: int) -> dict[str, Any]:
    """What iaso's records and log show of the run."""
    scratch = Path(scratch)
    records = sum(1 for d in RECORD_DIRS if (scratch / ".iaso" / d).is_dir()
                  for f in (scratch / ".iaso" / d).iterdir() if f.is_file())
    answered = sum(1 for t in transcript if t.source == "scripted-owner")
    failed = [t.text for t in transcript if t.role == "agent" and t.source == "error"]
    gates = proofs = stale = 0
    try:
        from iaso.api import open_core
        from iaso.capture import proof

        core = open_core(scratch)
        gates = sum(1 for _ in core.log_read("events", kinds=["intent-gate"]))
        ids = [i for i, r in core.index().items() if r.kind == "requirement"]
        proofs = len(ids) - len(proof.not_shown(core, ids))
        stale = sum(1 for s in core.link_states() if s.state in ("stale", "dangling"))
    except Exception:  # noqa: BLE001 - a store the agent broke scores as empty, not as a crash
        pass
    return {"records": records, "questions_asked": answered + unanswered,
            "questions_answered": answered, "gates": gates, "proofs": proofs, "stale": stale,
            "issues": len(issues), "errors": len(failed),
            "error": failed[0][:200] if failed else ""}


def line(task: str, model: str, score: dict[str, Any]) -> str:
    return (f"{task} {model}: checks {score['checks_passed']}/{score['checks_total']}, "
            f"records {score['records']}, questions {score['questions_answered']}/"
            f"{score['questions_asked']}, gates {score['gates']}, stale {score['stale']}, "
            f"issues {score['issues']}"
            + (f", failed turns {score['errors']}" if score.get("errors") else ""))
