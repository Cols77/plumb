"""SessionStart: the intent brief, a few lines plus a pointer (spec 6.1, ruling R9); the long
brief (about 30 lines, hard cap 40) with ``hooks.session_brief: full``.

Every line goes through the one emitter (``plumb.present.delta``, sp5 3): a resumed
session that already has a line gets nothing new. Context, never procedure: the brief
from ``CoreAPI.brief_lines`` plus one line of test evidence from ``VerifyAPI``. Also
writes ``.plumb/session/status.json`` so the status line has data from the first turn.

The records brief is computed first and kept (``HookContext.keep``): when the budget runs
out, the owner's records are still briefed and only the tests line reads ``not checked``.
The tests line is cached under the verify fingerprint, so a warm start builds no test map.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from plumb.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, run_hook
from plumb.hosts.claude_code.providers import LAZY, verify_api

HARD_CAP = 40
NOT_CHECKED = "tests: not checked (budget)"


def _clip_list(items: list[str], shown: int = 2) -> str:
    head = ", ".join(items[:shown])
    return head + (f", +{len(items) - shown} more" if len(items) > shown else "")


def tests_summary(core: Any, verify: Any) -> dict[str, Any]:
    """The brief's test evidence, as plain JSON (cached by the verify fingerprint)."""
    from plumb.hosts.claude_code.snapshot import tests_state

    pending = verify.full_pending()
    requirement_ids = [i for i, r in core.index().items() if r.kind == "requirement"]
    mapped = verify.tests_for(requirement_ids) if requirement_ids else {}
    nodes = sorted({n for tests in mapped.values() for n in tests})
    evidence = verify.evidence(nodes) if nodes else {}
    state, failing, regressions = tests_state(evidence)
    return {
        "nodes": len(nodes),
        "fresh": sum(e.state in ("fresh-pass", "flaky-pass") for e in evidence.values()),
        "state": state, "failing": list(failing), "regressions": list(regressions),
        "not_yet": sorted(n for n, e in evidence.items()
                          if e.state == "fresh-fail" and not e.regression),
        "pending": bool(pending.pending), "reasons": list(pending.reasons)}


def cached_summary(core: Any, verify: Any) -> dict[str, Any]:
    derived = getattr(verify, "derived", None)
    if derived is None:  # a VerifyAPI without the cache (tests' fakes)
        return tests_summary(core, verify)
    return derived("brief_tests", lambda: tests_summary(core, verify))


def evidence_line(summary: Mapping[str, Any] | None) -> str:
    if summary is None:
        return "tests: verification unavailable"
    parts: list[str] = []
    regressions, failing = list(summary["regressions"]), list(summary["not_yet"])
    if regressions:
        parts.append(f"{len(regressions)} regression ({_clip_list(regressions)})")
    if failing:
        parts.append(f"{len(failing)} failing ({_clip_list(failing)})")
    if not parts:
        nodes = int(summary["nodes"])
        parts.append(f"{summary['fresh']}/{nodes} mapped tests with fresh passing evidence"
                     if nodes else "no mapped tests yet (plumb tests map)")
    if summary["pending"]:
        parts.append("full verification pending (" + ", ".join(summary["reasons"]) + ")")
    return "tests: " + " | ".join(parts)


def brief(core: Any, tests_line: str) -> list[str]:
    """The compact brief by default (R9: a few lines plus a pointer); ``hooks.session_brief:
    full`` keeps the long brief of about 30 lines."""
    if str(core.config.hooks.session_brief) != "full":
        from plumb.query import compact_brief_lines

        lines = compact_brief_lines(core)
        lines.insert(len(lines) - 1, tests_line)
        return lines[:HARD_CAP]
    cap = min(int(core.config.hooks.brief_lines), HARD_CAP)
    lines = list(core.brief_lines(max(cap - 1, 1)))[: cap - 1]
    at = len(lines) - 1 if lines and lines[-1].startswith("open NCs") else len(lines)
    lines.insert(at, tests_line)
    return lines[:HARD_CAP]


def handle(ctx: HookContext, *, verify: Any = LAZY) -> HookOutput:
    """The records brief first (kept through any cut), then the tests line."""
    from plumb.api import open_core
    from plumb.contracts import FullPending
    from plumb.hosts.claude_code.snapshot import build_snapshot, write_snapshot
    from plumb.present.delta import Line, open_emitter, reset

    core = open_core(ctx.root)
    if ctx.data.get("source") != "resume":
        # a new conversation, /clear or compaction: the agent's context lost what earlier
        # hooks injected, so records come again (R9); a resumed one keeps its transcript
        reset(ctx.session_dir, ctx.session_id)
    emitter = open_emitter(ctx, "session-start", config=core.config)
    # no soft-budget check before the records brief: only the watchdog bounds it
    records_brief = brief(core, NOT_CHECKED)
    ctx.keep(emitter.add([Line(line) for line in records_brief], commit=False))
    verify = verify_api(core, verify)
    summary = None
    if verify is not None:
        ctx.deadline.check("tests")
        summary = cached_summary(core, verify)
    lines = emitter.add([Line(evidence_line(summary) if line == NOT_CHECKED else line)
                         for line in records_brief])
    ctx.keep(lines)
    emitter.close()
    if not ctx.deadline.expired():
        pending = None if summary is None else FullPending(summary["pending"],
                                                           tuple(summary["reasons"]))
        tests = None if summary is None else (summary["state"], tuple(summary["failing"]),
                                              tuple(summary["regressions"]))
        write_snapshot(ctx.root, build_snapshot(core, full_pending=pending, tests_summary=tests),
                       present=getattr(core.config, "present", None))
    return HookOutput(text="\n".join(lines))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY) -> int:
    return run_hook("session-start", lambda ctx: handle(ctx, verify=verify), stdin=stdin,
                    stdout=stdout, root=root, budget_ms=hook_budget("session_start"),
                    watchdog=watchdog, start=start)
