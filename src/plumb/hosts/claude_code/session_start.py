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

import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from plumb.hosts.claude_code.hookio import HookContext, HookOutput, hook_budget, run_hook
from plumb.hosts.claude_code.providers import LAZY, verify_api

HARD_CAP = 40
NOT_CHECKED = "tests: not checked (budget)"


class StepTimer:
    """Milliseconds per step, written to ``.plumb/session/<id>/timing.json`` only with
    ``PLUMB_HOOK_TIMING=1`` (a measurement aid; the hook records nothing otherwise)."""

    def __init__(self, ctx: HookContext) -> None:
        self.ctx = ctx
        self.on = os.environ.get("PLUMB_HOOK_TIMING") == "1"
        self.steps: dict[str, float] = {}
        if self.on:  # interpreter start and the hook module's imports, before the handler
            self.steps["imports"] = round(ctx.deadline.elapsed_s() * 1000, 1)
        self._last = time.monotonic()

    def mark(self, name: str) -> None:
        """Close the step ``name``: the time since the previous mark."""
        if not self.on:
            return
        now = time.monotonic()
        self.steps[name] = round(self.steps.get(name, 0.0) + (now - self._last) * 1000, 1)
        self._last = now

    def write(self) -> None:
        if not self.on:
            return
        from plumb.hosts.claude_code.hookio import write_json_atomic

        try:
            write_json_atomic(self.ctx.session_dir / self.ctx.session_id / "timing.json",
                              {"steps": self.steps, "total_ms": round(
                                  self.ctx.deadline.elapsed_s() * 1000, 1)})
        except OSError:
            pass


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


BACKGROUND = "tests: not checked (checking in the background)"


def cached_summary(core: Any, verify: Any) -> dict[str, Any]:
    derived = getattr(verify, "derived", None)
    if derived is not None:
        verify.full_pending()  # a cold test map raises inside and starts its detached build
        if getattr(verify, "map_missing", None) is not None:
            return {"background": True}  # never cached: the next start reads the built map
    if derived is None:  # a VerifyAPI without the cache (tests' fakes)
        return tests_summary(core, verify)
    return derived("brief_tests", lambda: tests_summary(core, verify))


def evidence_line(summary: Mapping[str, Any] | None) -> str:
    if summary is None:
        return "tests: verification unavailable"
    if summary.get("background"):
        return BACKGROUND
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


def _judgment_timeout_s(core: Any) -> float:
    try:
        return max(float(core.config.judgment.hook_timeout_ms), 0.0) / 1000.0
    except (AttributeError, TypeError, ValueError):
        return 0.0


LOCAL_BACKENDS = ("heuristic", "disabled", "fake")


def triage_offer_line(core: Any) -> str | None:
    """The brief's one triage line (R8 A, sp5 3): the records rated faithful to the owner's
    words, from CAPTURE's triage; None without CAPTURE or without a low-risk group.

    Read from the last whole triage's cache when there is one (no judgment, no import of the
    judgment modules); with none, only a backend that runs on this machine is asked, never
    one that calls the network: a cold start waits for a triage run (SR-014)."""
    try:
        from plumb.capture import triage as cached
    except ImportError:
        return None
    try:
        known, line = cached.cached_offer(core)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the brief
        known, line = False, None
    if known:
        return line
    if str(getattr(getattr(core.config, "judgment", None), "backend", "heuristic")
           ).strip().lower() not in LOCAL_BACKENDS:
        return None
    try:
        from plumb.capture import api
    except ImportError:
        return None
    try:
        view = api.triage(core, None)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the brief
        return None
    low = list(getattr(view, "low_risk", ()) or ())
    if not low:
        return None
    noun = "record" if len(low) == 1 else "records"
    return (f"plumb: {len(low)} {noun} rated faithful to your words await you: "
            "plumb triage lists them; plumb confirm shows them as cards")


def auto_approve_off(core: Any) -> str | None:
    """``off`` when the owner never turned auto-approve on (no owner ``config`` event), known
    without the judgment modules the full state would import; None when it must be worked
    out (CAPTURE's ``auto_approve_state``, which snapshot defaults to)."""
    for entry in core.events():
        if entry.kind == "config" and entry.marker == "none"                 and entry.payload.get("by") == "owner"                 and isinstance(entry.payload.get("auto_approve"), Mapping):
            return None
    return None if core.config.auto_approve.enabled else "off"


def conflicts_line(core: Any) -> str | None:
    """One line counting the open intent conflicts (sp6 8.3); the cards come with
    /plumb conflicts or the stop hook."""
    try:
        from plumb.hosts.claude_code.snapshot import open_conflict_count
        from plumb.present.owner_text import CONFLICTS_BRIEF
    except ImportError:
        return None
    count = open_conflict_count(core)
    return CONFLICTS_BRIEF.format(n=count) if count else None


def handle(ctx: HookContext, *, verify: Any = LAZY) -> HookOutput:
    """The records brief first (kept through any cut), then the tests line."""
    timer = StepTimer(ctx)
    try:
        return _handle(ctx, verify, timer)
    finally:
        timer.write()


def _handle(ctx: HookContext, verify: Any, timer: StepTimer) -> HookOutput:
    from plumb.api import open_core
    from plumb.contracts import FullPending
    from plumb.hosts.claude_code.hygiene import GIT_TIMEOUT_S, TreeScan
    from plumb.hosts.claude_code.snapshot import build_snapshot, write_snapshot
    from plumb.present.delta import Line, open_emitter, reset

    timer.mark("imports")
    # work left in the tree from before is told only at the start of a conversation
    scan = TreeScan(ctx.root) if ctx.data.get("source") not in ("resume", "compact") else None
    core = open_core(ctx.root)
    timer.mark("core_open")
    if ctx.data.get("source") != "resume":
        # a new conversation, /clear or compaction: the agent's context lost what earlier
        # hooks injected, so records come again (R9); a resumed one keeps its transcript
        reset(ctx.session_dir, ctx.session_id)
    emitter = open_emitter(ctx, "session-start", config=core.config)
    if timer.on:
        core.index()
        timer.mark("index")
    # no soft-budget check before the records brief: only the watchdog bounds it
    records_brief = brief(core, NOT_CHECKED)
    ctx.keep(emitter.add([Line(line) for line in records_brief], commit=False))
    timer.mark("brief")
    # the status line's snapshot as soon as the records are read, tests unknown: the tests
    # check can outlast the hook's watchdog, which must not leave the line on an older session
    present = getattr(core.config, "present", None)
    auto_off = auto_approve_off(core)
    write_snapshot(ctx.root, build_snapshot(core, auto_approve=auto_off), present=present)
    timer.mark("snapshot")
    verify = verify_api(core, verify)
    summary = None
    if verify is not None:
        ctx.deadline.check("tests")
        summary = cached_summary(core, verify)
    timer.mark("tests_summary")
    lines = emitter.add([Line(evidence_line(summary) if line == NOT_CHECKED else line)
                         for line in records_brief])
    ctx.keep(lines)
    conflicts = conflicts_line(core)  # sp6 8.3: a merge left intent awaiting the owner
    if conflicts:
        lines += emitter.add([Line(conflicts)])
        ctx.keep(lines)
    if summary is not None and not summary.get("background"):
        # the tests known: the snapshot again, before the optional lines
        pending = FullPending(summary["pending"], tuple(summary["reasons"]))
        tests = (summary["state"], tuple(summary["failing"]), tuple(summary["regressions"]))
        write_snapshot(ctx.root, build_snapshot(core, full_pending=pending, tests_summary=tests,
                                      auto_approve=auto_off),
                       present=present)
    timer.mark("snapshot")
    leftover = None if scan is None else scan.line(min(GIT_TIMEOUT_S, ctx.deadline.remaining_s()))
    timer.mark("tree_scan")
    if leftover:  # INT-027: work from before this session, said before any new work
        del lines[HARD_CAP - 1:]  # the cap holds: at worst the brief's last line makes room
        lines += emitter.add([Line(leftover)])
        ctx.keep(lines)
    if not ctx.deadline.expired():  # sp6 9.4: other worktrees and branches, R17 conflicts
        from plumb.awareness.turn import at_session_start

        lines += emitter.add(at_session_start(core, ctx.deadline))
        ctx.keep(lines)
    timer.mark("awareness")
    # R8 A: at most one line, the triage offer. Its judgment may call the network for up to
    # the hook timeout, so it runs only when that much of the budget is left (the cached
    # judgments of an earlier session make it free; a cold one waits for a roomier hook)
    if ctx.deadline.remaining_s() > _judgment_timeout_s(core):
        offer = triage_offer_line(core)
        if offer:
            lines += emitter.add([Line(offer)])
            ctx.keep(lines)
    timer.mark("triage_offer")
    emitter.close()
    return HookOutput(text="\n".join(lines))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY) -> int:
    return run_hook("session-start", lambda ctx: handle(ctx, verify=verify), stdin=stdin,
                    stdout=stdout, root=root, budget_ms=hook_budget("session_start"),
                    watchdog=watchdog, start=start)
