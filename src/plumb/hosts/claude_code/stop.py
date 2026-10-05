"""Stop: covering tests within the budget, the three triggers, then the summary (spec 6.4).

1. This turn's changed paths: the session's ``touched.txt`` plus every path of one
   ``git status`` call whose mtime is at or after the turn start.
2. Their records (``CoreAPI.records_for_paths``), the link states of those records only, the
   covering selection (``VerifyAPI.select``) and its evidence.
3. Write ``status.json`` and the stated set (``stated.json``). Each stated record carries
   ``shown``: true only when the summary displayed its whole read-back (statement, every
   example, will/won't, labelled assumptions, alternatives). A bare affirmation relays only
   shown records; a record cut by ``hooks.summary_proposed_cap`` (counted in records) or too
   long to show, or any record of a blocked stop, must be named in the owner's words.
4. At most one block per turn, never when the host says ``stop_hook_active``: covering tests
   without fresh evidence (the agent runs ``plumb tests run --paths <this turn's paths>`` in
   its turn; the hook never runs pytest), an unconfirmed decision that matters (trigger 2,
   once per hash) and a regression (trigger 3, R3: a node that passed with recorded
   evidence and now fails; once per failing run). A new test that starts red is "not yet
   passing" and never asks.
5. Otherwise a short ``systemMessage`` summary; proposed records are shown, never asked,
   and the ones not shown are named with the ``plumb show`` command that prints them.

The deadline is checked before a step starts, never after it ends (spec 10): a step that
would start past the soft budget is skipped and named in a ``check skipped (budget)`` notice,
and results already computed are always used (the stated set, the snapshot, the block and the
summary). Only when the record states themselves cannot start does the hook fall back to the
bare budget notice. The watchdog's hard limit still bounds the whole hook.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from plumb.hosts.claude_code.hookio import (
    HookContext,
    HookOutput,
    hook_budget,
    read_json,
    run_hook,
    write_json_atomic,
)
from plumb.hosts.claude_code.providers import LAZY, unjudged_fn, verify_api

IGNORED_PREFIXES = (".plumb/session/", ".plumb/cache/", ".plumb/log/", ".git/")
IGNORED_FILES = (".plumb/test_map.txt",)
SUMMARY_LINES = 5
GIT_TIMEOUT_S = 0.6
MAX_INSTRUCTION_PATHS = 8
MAX_PROPOSED_LINE = 400


def _clip(text: str, width: int = 120) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _ignored(rel: str) -> bool:
    return rel.startswith(IGNORED_PREFIXES) or rel in IGNORED_FILES


def _touched(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip()]


def git_changed(root: Path, timeout: float = GIT_TIMEOUT_S) -> list[str]:
    """Paths of one ``git status --porcelain -z --untracked-files=all`` call."""
    try:
        result = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                                cwd=root, capture_output=True, timeout=max(timeout, 0.05),
                                check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    out: list[str] = []
    entries = result.stdout.decode("utf-8", errors="replace").split("\0")
    skip_next = False
    for entry in entries:
        if skip_next:
            skip_next = False
            continue
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            skip_next = True  # the next entry is the original path
        out.append(path)
    return out


def changed_paths(root: Path, touched_file: Path, turn_start: float,
                  timeout: float = GIT_TIMEOUT_S) -> list[str]:
    seen: dict[str, None] = {}
    for rel in _touched(touched_file):
        if not _ignored(rel):
            seen.setdefault(rel, None)
    if turn_start > 0:
        for rel in git_changed(root, timeout):
            if rel in seen or _ignored(rel):
                continue
            try:
                mtime = os.stat(root / rel).st_mtime
            except OSError:
                continue
            if mtime >= turn_start:
                seen.setdefault(rel, None)
    return list(seen)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _dec_question(record: Any) -> str:
    chosen = str(record.fields.get("chosen") or "A").strip()
    alternatives = record.fields.get("alternatives") or []
    if isinstance(alternatives, str):
        alternatives = [alternatives]
    other = str(alternatives[0]).strip() if alternatives else "another reading"
    return (f"plumb: {record.id} is unconfirmed and this work relies on it. Ask the owner: "
            f"\"I assumed {chosen}; {other} also fits. Which one?\"")


def matters_decisions(index: Mapping[str, Any], statuses: Mapping[str, Any],
                      touched: Iterable[str]) -> list[str]:
    """Unconfirmed DECs with ``matters: true`` that are touched or decide a touched record."""
    touched = set(touched)
    out = []
    for record_id, record in sorted(index.items()):
        if record.kind != "decision" or record.fields.get("matters") is not True:
            continue
        linked = {link.target.record for link in record.links if link.target.record}
        if record_id not in touched and not (linked & touched):
            continue
        status = statuses.get(record_id)
        if status is not None and status.confirmation == "confirmed":
            continue
        out.append(record_id)
    return out


def _regression_line(node: str, evidence: Any) -> str:
    note = " (test source changed since the pass)" if evidence.test_changed_since_pass else ""
    run = f" (last run {evidence.last_run})" if evidence.last_run else ""
    return (f"plumb: regression: {node} passed in an earlier run and now fails{note}{run}. "
            "Tell the owner, with a read-back, and ask how to proceed.")


def proposed_lines(index: Mapping[str, Any], stated_ids: Sequence[str],
                   cap: int) -> tuple[list[str], list[str]]:
    """The ``proposed`` lines of the summary and the ids shown in full.

    ``cap`` counts records, never lines: a shown record shows every line of its read-back
    (``plumb.readback.record_lines``). A record past the cap, or with a line longer than
    ``MAX_PROPOSED_LINE``, is not shown at all; the last line names it with the ``plumb
    show`` command that prints it, and a confirmation must name it.
    """
    from plumb.readback import record_lines

    lines: list[str] = []
    shown: list[str] = []
    cut: list[str] = []
    for record_id in stated_ids:
        rendered = [f"plumb: proposed {line}" for line in record_lines(index[record_id])]
        if len(shown) >= max(cap, 0) or any(len(line) > MAX_PROPOSED_LINE
                                            for line in rendered):
            cut.append(record_id)
            continue
        lines.extend(rendered)
        shown.append(record_id)
    if cut:
        lines.append(f"plumb: +{len(cut)} more not shown: {', '.join(cut)} "
                     f"(plumb show {' '.join(cut)}); a confirmation must name them")
    return lines, shown


def write_stated(ctx: HookContext, turn: Mapping[str, Any], index: Mapping[str, Any],
                 stated_ids: Sequence[str], shown: Iterable[str] = ()) -> None:
    """The stated set of this reply: what a bare affirmation of the owner may confirm."""
    from plumb.normalize import utc_now

    shown = set(shown)
    write_json_atomic(ctx.session_dir / "stated.json",
                      {"at": utc_now(), "session": ctx.session_id,
                       "reply_after_prompt": turn.get("prompt_digest"),
                       "records": [{"id": i, "hash": index[i].hash, "shown": i in shown}
                                   for i in stated_ids]})


def _confirmations(core: Any, since: float) -> list[str]:
    if since <= 0:
        return []
    start = _iso(since)
    out = []
    for entry in core.log_read("events", kinds=["approval"]):
        if entry.at < start:
            continue
        ids = ", ".join(str(r.get("id")) for r in entry.payload.get("records") or [])
        if entry.payload.get("by") == "agent-relayed":
            quote = _clip(entry.payload.get("quote"), 60)
            out.append(f"confirmed {ids} on your prompt \"{quote}\"")
        else:
            out.append(f"confirmed {ids} by the owner")
    return out


def handle(ctx: HookContext, *, verify: Any = LAZY, unjudged: Any = LAZY) -> HookOutput | None:
    active = bool(ctx.data.get("stop_hook_active"))
    session_dir = ctx.session_dir / ctx.session_id
    turn_path = session_dir / "turn.json"
    turn = read_json(turn_path)
    turn = turn if isinstance(turn, dict) else {}
    try:
        turn_start = float(turn.get("turn_start") or 0)
    except (TypeError, ValueError):
        turn_start = 0.0
    asked = turn.get("asked") if isinstance(turn.get("asked"), dict) else {}
    changed = changed_paths(ctx.root, session_dir / "touched.txt", turn_start,
                            min(GIT_TIMEOUT_S, max(ctx.deadline.remaining_s(), 0.05)))
    from plumb.api import open_core
    from plumb.hosts.claude_code.snapshot import build_snapshot, write_snapshot

    core = open_core(ctx.root)
    if not changed:
        write_stated(ctx, turn, {}, [])
        return None
    skipped: list[str] = []
    ctx.deadline.check("record states")  # nothing below can run without them
    index = core.index()
    by_path = core.records_for_paths(changed)
    touched_ids = sorted({i for ids in by_path.values() for i in ids if i in index})
    changed_set = set(changed)
    edited_ids = [i for i in touched_ids if index[i].path in changed_set]
    all_statuses = core.status()

    verify = verify_api(core, verify)
    selection = evidence = pending = None
    if verify is not None:
        if ctx.deadline.expired():
            skipped.append("covering tests")
        else:
            selection = verify.select(changed,
                                      budget_s=float(core.config.verify.turn_budget_s))
            evidence = dict(verify.evidence(selection.nodes)) if selection.nodes else {}
            pending = verify.full_pending()

    # trigger 2: decisions that matter, unconfirmed, touched this turn
    decisions = matters_decisions(index, all_statuses, touched_ids)
    open_decisions = [d for d in decisions if asked.get(d) != index[d].hash]
    # trigger 3: regressions (R3), asked once per failing run
    regressions = sorted(n for n, e in (evidence or {}).items() if e.regression)
    open_regressions = [n for n in regressions
                        if asked.get(f"regression:{n}") != (evidence[n].last_run or "?")]
    not_run = [n for n, e in (evidence or {}).items() if e.state in ("none", "stale")]

    stated_ids = [i for i in edited_ids
                  if all_statuses[i].confirmation != "confirmed"]
    for d in decisions:
        if d not in stated_ids:
            stated_ids.append(d)
    # nothing is shown yet: a blocked stop (or a hook cut short) shows the owner nothing
    write_stated(ctx, turn, index, stated_ids)

    unjudged = unjudged_fn(unjudged)
    requirement_ids = [i for i in touched_ids if index[i].kind == "requirement"]
    fidelity = ()
    if unjudged is not None and requirement_ids:
        if ctx.deadline.expired():
            skipped.append("fidelity")
        else:
            try:
                fidelity = tuple(unjudged(core, requirement_ids))
            except Exception:  # noqa: BLE001 - advisory only
                fidelity = ()
    questions = [f"regression {n}" for n in regressions] + decisions
    write_snapshot(ctx.root, build_snapshot(
        core, evidence=evidence, full_pending=pending, statuses=all_statuses,
        deferred=len(selection.deferred) if selection else 0, fidelity_unjudged=fidelity,
        ask=len(questions), skipped=", ".join(skipped) or None))

    if not active:
        reasons: list[str] = []
        if not_run:
            reasons.append(tests_instruction(changed, float(core.config.verify.turn_budget_s)))
        for d in open_decisions:
            reasons.append(_dec_question(index[d]))
            asked[d] = index[d].hash
        for n in open_regressions:
            reasons.append(_regression_line(n, evidence[n]))
            asked[f"regression:{n}"] = evidence[n].last_run or "?"
        if reasons:
            if skipped:
                reasons.append(skip_notice(skipped))
            write_json_atomic(turn_path, {**turn, "asked": asked})
            return HookOutput(block_reason="\n".join(reasons))

    if ctx.deadline.expired():
        skipped.append("confirmations")
        turn_start = 0.0  # _confirmations reads no log without a turn start
    text, shown = summary(
        core, index, all_statuses, changed, touched_ids, stated_ids, selection, evidence,
        pending, questions, fidelity, turn_start, verify is not None, skipped)
    if shown:
        write_stated(ctx, turn, index, stated_ids, shown)
    return HookOutput(system_message=text)


def _quote(path: str) -> str:
    return f'"{path}"' if any(c.isspace() for c in path) else path


def tests_instruction(changed: Sequence[str], budget: float) -> str:
    """The test command for this turn: ``--paths`` names the turn's own changed paths, so
    other uncommitted work in the tree cannot crowd its covering tests out of the budget
    (``--changed`` covers every uncommitted path); ``--changed`` only for a long list."""
    if 0 < len(changed) <= MAX_INSTRUCTION_PATHS:
        command = "plumb tests run --paths " + " ".join(_quote(p) for p in changed)
        scope = "covering tests of this turn"
    else:
        command, scope = "plumb tests run --changed", "covering tests"
    return f"plumb: run '{command}' ({scope}, budget {budget:g} s), then finish your reply."


def skip_notice(skipped: Sequence[str]) -> str:
    """The notice naming the steps that would have started past the deadline (spec 10)."""
    return "plumb: check skipped (budget): " + ", ".join(skipped)


def summary(core: Any, index: Mapping[str, Any], statuses: Mapping[str, Any],
            changed: Sequence[str], touched_ids: Sequence[str], stated_ids: Sequence[str],
            selection: Any, evidence: Mapping[str, Any] | None, pending: Any,
            questions: Sequence[str], fidelity: Sequence[str], turn_start: float,
            verify_available: bool, skipped: Sequence[str] = ()) -> tuple[str, list[str]]:
    """The summary text and the stated ids it showed in full."""
    records_edited = any(index[i].path in set(changed) for i in touched_ids)
    doc_only = (selection.doc_only if selection is not None else
                all(p.endswith(".md") or p.startswith("docs/") for p in changed))
    stale = [s for i in touched_ids for s in statuses[i].links if s.state == "stale"]
    touched = ("plumb: touched " + ", ".join(touched_ids) if touched_ids
               else f"plumb: touched {len(changed)} file(s), no records")
    if stale:
        first = stale[0]
        target = first.link.target
        end = target.record or target.path or target.test or target.symbol or "?"
        touched += f" | stale: {first.link.id} -> {end} ({first.moved} moved)"
        if len(stale) > 1:
            touched += f" +{len(stale) - 1} more"
    if doc_only and not records_edited:
        return touched + " | docs only, no tests selected", []
    lines = [touched]
    if not verify_available:
        lines.append("plumb: verification unavailable")
    elif selection is not None:
        ev = evidence or {}
        fresh_pass = sum(e.state in ("fresh-pass", "flaky-pass") for e in ev.values())
        regression = sum(e.regression for e in ev.values())
        not_yet = sum(e.state == "fresh-fail" and not e.regression for e in ev.values())
        not_run = sum(e.state in ("none", "stale") for e in ev.values())
        parts = [f"{fresh_pass} fresh pass"]
        if regression:
            parts.append(f"{regression} regression")
        parts.append(f"{not_yet} not yet passing")
        if not_run:
            parts.append(f"{not_run} not run")
        parts.append(f"{len(selection.deferred)} deferred (budget)")
        lines.append(f"plumb: covering tests {len(selection.nodes)}: " + ", ".join(parts))
    if pending is not None and pending.pending:
        lines.append("plumb: full verification pending (" + ", ".join(pending.reasons) + ")")
    confirmed = _confirmations(core, turn_start)
    extra = []
    if confirmed:
        extra.append("; ".join(confirmed))
    if fidelity:
        extra.append("fidelity unjudged: " + ", ".join(fidelity))
    if skipped:
        extra.append(skip_notice(skipped).removeprefix("plumb: "))
    if extra:
        lines.append(_clip("plumb: " + " | ".join(extra), 200))
    lines.append("plumb: questions: " + ("; ".join(questions) if questions else "none"))
    lines = lines[:SUMMARY_LINES]
    proposed, shown = proposed_lines(index, stated_ids,
                                     int(core.config.hooks.summary_proposed_cap))
    lines.extend(proposed)
    return "\n".join(lines), shown


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, unjudged: Any = LAZY) -> int:
    return run_hook("stop", lambda ctx: handle(ctx, verify=verify, unjudged=unjudged),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("stop"),
                    json_output=True, watchdog=watchdog, start=start)
