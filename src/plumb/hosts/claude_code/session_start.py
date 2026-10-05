"""SessionStart: the intent brief, about 30 lines, hard cap 40 (spec 6.1).

Context, never procedure: the brief from ``CoreAPI.brief_lines`` plus one line of test
evidence from ``VerifyAPI``. Also writes ``.plumb/session/status.json`` so the status line
has data from the first turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from plumb.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, run_hook
from plumb.hosts.claude_code.providers import LAZY, verify_api

HARD_CAP = 40


def _clip_list(items: list[str], shown: int = 2) -> str:
    head = ", ".join(items[:shown])
    return head + (f", +{len(items) - shown} more" if len(items) > shown else "")


def evidence_line(core: Any, verify: Any) -> tuple[str, Mapping[str, Any] | None, Any]:
    """``(line, evidence, full_pending)`` for the brief's tests line."""
    if verify is None:
        return "tests: verification unavailable", None, None
    pending = verify.full_pending()
    requirement_ids = [i for i, r in core.index().items() if r.kind == "requirement"]
    mapped = verify.tests_for(requirement_ids) if requirement_ids else {}
    nodes = sorted({n for tests in mapped.values() for n in tests})
    evidence = verify.evidence(nodes) if nodes else {}
    regressions = sorted(n for n, e in evidence.items() if e.regression)
    failing = sorted(n for n, e in evidence.items() if e.state == "fresh-fail"
                     and not e.regression)
    parts: list[str] = []
    if regressions:
        parts.append(f"{len(regressions)} regression ({_clip_list(regressions)})")
    if failing:
        parts.append(f"{len(failing)} failing ({_clip_list(failing)})")
    if not parts:
        fresh = sum(e.state in ("fresh-pass", "flaky-pass") for e in evidence.values())
        parts.append(f"{fresh}/{len(nodes)} mapped tests with fresh passing evidence"
                     if nodes else "no mapped tests yet (plumb tests map)")
    if pending.pending:
        parts.append("full verification pending (" + ", ".join(pending.reasons) + ")")
    return "tests: " + " | ".join(parts), evidence, pending


def brief(core: Any, verify: Any) -> tuple[list[str], Mapping[str, Any] | None, Any]:
    cap = min(int(core.config.hooks.brief_lines), HARD_CAP)
    tests, evidence, pending = evidence_line(core, verify)
    lines = list(core.brief_lines(max(cap - 1, 1)))[: cap - 1]
    at = len(lines) - 1 if lines and lines[-1].startswith("open NCs") else len(lines)
    lines.insert(at, tests)
    return lines[:HARD_CAP], evidence, pending


def handle(ctx: HookContext, *, verify: Any = LAZY) -> HookOutput:
    from plumb.api import open_core
    from plumb.hosts.claude_code.snapshot import build_snapshot, write_snapshot

    core = open_core(ctx.root)
    verify = verify_api(core, verify)
    ctx.deadline.check("open core")
    lines, evidence, pending = brief(core, verify)
    if not ctx.deadline.expired():
        write_snapshot(ctx.root, build_snapshot(core, evidence=evidence, full_pending=pending))
    return HookOutput(text="\n".join(lines))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY) -> int:
    return run_hook("session-start", lambda ctx: handle(ctx, verify=verify), stdin=stdin,
                    stdout=stdout, root=root, budget_ms=hook_budget("session_start"),
                    watchdog=watchdog, start=start)
