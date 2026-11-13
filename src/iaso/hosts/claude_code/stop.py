"""Stop: the one next action of a turn (SR-373), within what its reader needs (SR-375).

Inline, in this order: queue the rest for the background worker (the owner-words
confirmations, the upkeep, the jobs: ``summary.queue_after_stop``, delivered through the
agent's notes at the next prompt); this turn's changed paths (the session's ``touched.txt``
plus every path of one ``git status`` call whose mtime is at or after the turn start); their
records and the stated set (nothing is drawn, so a bare "ok" confirms nothing); the status
line (``status.json``); the covering selection (``VerifyAPI.select``) and its evidence; the
regression check; then the one next action, as a block for the agent, chosen in this order:
a regression > covering tests lacking a fresh run (the agent runs ``iaso tests run --paths``;
the hook never runs pytest) > a file no requirement owns > the links this turn moved (the stale
hold, SR-111) > the judge's questions that block its next task. Each goes through the one
emitter (``iaso.present.delta``), once per session per state; one already said gives way to
the next. Never when the host says ``stop_hook_active``, except the stale hold.

The owner gets one plain line only when something needs them (``summary.owner_line``): a
regression on confirmed behaviour, a merge that waits; nothing inside an intent loop. Each
step is marked for the profile (``HookContext.mark``, ``IASO_HOOK_PROFILE=1``).

The deadline is checked before a step starts, never after it ends (spec 10): a step that
would start past the soft budget is skipped and named in the status line."""

from __future__ import annotations

from iaso.paths import state_dir

import hashlib
import os
import re
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple, TextIO

from iaso.hosts.claude_code.hookio import (
    Deadline,
    HookContext,
    HookOutput,
    hard_limit_s,
    hook_budget,
    read_json,
    run_hook,
    write_json_atomic,
)
from iaso.hosts.claude_code.providers import LAZY, verify_api
from iaso.trace import is_code_path

IGNORED_PREFIXES = (".iaso/session/", ".iaso/cache/", ".iaso/log/", ".iaso/view/", ".git/")
IGNORED_FILES = (".iaso/test_map.txt",)
GIT_TIMEOUT_S = 5.0  # a slice of the soft budget: under load git status alone can take 0.6 s
STOP_GRACE_S = 1.0  # past the hard limit, only while the read-back is not yet kept (R1)
GIT_SKIPPED = "change detection (git status)"
MAX_INSTRUCTION_PATHS = 8
HARD_RESERVE_S = 10.0  # kept under the watchdog's hard limit for the steps after a long one


def time_left_s(ctx: HookContext) -> float:
    """SR-310: the time a step that starts work may take: what is left of the soft budget, and
    never more than what is left under the watchdog's hard limit less ``HARD_RESERVE_S`` (both
    clocks run from the same start), so a step that keeps to it ends before the watchdog
    fires, whatever the configured budget (case hook-stop-e98405d1)."""
    hard = hard_limit_s(ctx.root)
    # a hard limit set under twice the reserve keeps half of itself, not no time at all
    under_hard = hard - ctx.deadline.elapsed_s() - min(HARD_RESERVE_S, hard / 2)
    return max(min(ctx.deadline.remaining_s(), under_hard), 0.0)


def capped_deadline(ctx: HookContext) -> Deadline:
    """The deadline of a step that takes one (the awareness git work): ``time_left_s`` from
    now, so a soft budget set past the hard limit cannot carry it into the watchdog."""
    return Deadline(time_left_s(ctx) * 1000.0)


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
    return _git_status(root, timeout) or []


def _git_status(root: Path, timeout: float) -> list[str] | None:
    """Like ``git_changed``; None when the call timed out (a loaded machine)."""
    try:
        result = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                                cwd=root, capture_output=True, timeout=max(timeout, 0.05),
                                check=False)
    except subprocess.TimeoutExpired:
        return None
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


class GitStatusJob:
    """``git status`` running beside the work that does not need it (the record index), so
    a loaded machine pays for the two at once; ``changed_paths`` collects the answer."""

    def __init__(self, root: Path, timeout: float = GIT_TIMEOUT_S) -> None:
        import threading

        self.result: list[str] | None = None
        self._thread = threading.Thread(target=self._run, args=(root, timeout), daemon=True)
        self._thread.start()

    def _run(self, root: Path, timeout: float) -> None:
        try:
            self.result = _git_status(root, timeout)
        except Exception:  # noqa: BLE001 - no answer reads as a timeout, named in the notice
            self.result = None

    def wait(self) -> list[str] | None:
        self._thread.join()
        return self.result


def changed_paths(root: Path, touched_file: Path, turn_start: float,
                  timeout: float = GIT_TIMEOUT_S,
                  skipped: list[str] | None = None,
                  job: GitStatusJob | None = None) -> list[str]:
    """This turn's paths. A ``git status`` that timed out is named in ``skipped``; ``job`` is
    a ``git status`` already started."""
    seen: dict[str, None] = {}
    for rel in _touched(touched_file):
        if not _ignored(rel):
            seen.setdefault(rel, None)
    if turn_start > 0:
        status = job.wait() if job is not None else _git_status(root, timeout)
        if status is None and skipped is not None:
            skipped.append(GIT_SKIPPED)
        for rel in status or ():
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


def masked_acceptance(core: Any, verify: Any, index: Mapping[str, Any],
                      statuses: Mapping[str, Any], touched_ids: Sequence[str],
                      changed: Sequence[str]) -> list[dict[str, Any]]:
    """Regressions of this turn's confirmed acceptance tests that a change to the test hid
    (``VerifyAPI.masked_regressions``), checked only when a changed path is a ``verified_by``
    end of a touched requirement (cheap otherwise)."""
    if verify is None or not hasattr(verify, "masked_regressions"):
        return []
    changed_set = set(changed)
    ends = {(link.target.test or link.target.path or "").split("::", 1)[0]
            for i in touched_ids if index[i].kind == "requirement"
            for link in index[i].links if link.kind == "verified_by"}
    files = sorted(ends & changed_set)
    if not files:
        return []
    scoped = {i: statuses[i] for i in touched_ids if i in statuses}
    try:
        return list(verify.masked_regressions(files=files, statuses=scoped))
    except Exception:  # noqa: BLE001 - a lane failure degrades, never breaks the stop
        return []


def _masked_line(index: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    parts = []
    for record_id, examples in (item.get("requirements") or {}).items():
        record = index.get(record_id)
        texts = []
        for example in (record.examples if record is not None else ()):
            if example.id in examples:
                texts.append(f"{example.id} \"" + (example.criterion or (
                    f"given {example.given}, when {example.when}, then {example.then}"))
                    + "\"")
        parts.append(f"{record_id} " + ("; ".join(texts) if texts else "(no example named)"))
    judge = item.get("judge") or {}
    if judge.get("failed"):  # SR-245: name the judge and the reason when none could answer
        judged = (f" No judge could read the change ({judge['failed']['judge']}): "
                  f"{judge['failed']['reason']}; the flag stays.")
    elif judge.get("pending"):
        judged = " A judge is reading the change; the flag stays until it answers."
    elif judge.get("verdict"):
        judged = " A judge read the change as made just so the test passes."
    else:
        judged = ""
    return _clip(f"iaso: regression hidden: {item['node']} passed in run "
                 f"{item.get('passed_in') or '?'}, then failed, and passes now only because "
                 f"the test itself was changed. It verifies {'; '.join(parts)}, which the "
                 f"owner confirmed.{judged} Tell the owner, with a read-back of the code and "
                 "test change, and ask how to proceed; a test is not rewritten to pass.", 600)


def _regression_line(node: str, evidence: Any) -> str:
    note = " (test source changed since the pass)" if evidence.test_changed_since_pass else ""
    run = f" (last run {evidence.last_run})" if evidence.last_run else ""
    return (f"iaso: regression: {node} passed in an earlier run and now fails{note}{run}. "
            "Tell the owner, with a read-back, and ask how to proceed.")


def write_stated(ctx: HookContext, turn: Mapping[str, Any], index: Mapping[str, Any],
                 stated_ids: Sequence[str], shown: Iterable[str] = (), *,
                 early: Sequence[Mapping[str, Any]] = (),
                 conflicts: Sequence[Mapping[str, Any]] = ()) -> None:
    """The stated set of this reply: what a bare affirmation of the owner may confirm.

    The one writer of ``stated.json``, so it holds the guarantee "``shown`` only when the
    owner sees the card" for every host: a drawn card reaches the owner only while iaso's
    panel is active (``present.json``), otherwise the agent's channel alone (SR-295) (``ctx.extra["display"]``, set by
    ``hosts.neutral.handle_event``): ``owner`` (the host shows ``owner_lines``) keeps
    ``shown``; ``unseen`` (the host could not show them) writes no record as shown;
    ``status`` (a status refresh, e.g. Codex's ``notify``) leaves the stated set of the reply
    the owner actually answers untouched."""
    from iaso.normalize import utc_now

    display = ctx.extra.get("display", "owner")
    if display == "status":
        return
    seen = display == "owner"
    # SR-295: cards go to the agent's channel; a drawn card reached the owner only on the panel
    shown = set(shown) if seen and _panel_shows(ctx, turn) else set()
    data: dict[str, Any] = {
        "at": utc_now(), "session": ctx.session_id,
        "reply_after_prompt": turn.get("prompt_digest"),
        "records": [{"id": i, "hash": index[i].hash, "shown": i in shown} for i in stated_ids]}
    if seen and conflicts:  # sp6 8.4: the conflict cards this reply showed the owner
        data["conflicts"] = [dict(c) for c in conflicts]
    if seen and early:  # R17: the early conflict cards this reply showed the owner
        data["early"] = [dict(c) for c in early]
    write_json_atomic(ctx.session_dir / "stated.json", data)


def _panel_shows(ctx: HookContext, turn: Mapping[str, Any]) -> bool:
    """The panel is active this turn, so the drawn cards reach the owner (``present.json``)."""
    try:
        from iaso.mod.handshake import active

        return active(ctx.root, ctx.session_id, float(turn.get("turn_start") or 0))
    except Exception:  # noqa: BLE001 - unknown means unseen: a bare "ok" confirms nothing
        return False


def _unchanged(ctx: HookContext, core: Any, turn: Mapping[str, Any],
               skipped: Sequence[str]) -> HookOutput | None:
    """A turn with no edit (SR-373 EX-4): nothing for the agent, the owner's line only when
    something needs them."""
    if skipped:  # a timed-out git status is no evidence of a turn without changes
        note_skipped(ctx.root, skipped)
    from iaso.awareness.early import stated_entry

    # R17: an early conflict asked before any record was written: the owner's answer to it
    # raises its decision (``answer.raise_shown``)
    write_stated(ctx, turn, {}, [], conflicts=conflict_entries(core),
                 early=[stated_entry(c) for c in early_conflicts(ctx, core, turn)])
    return owner_output(ctx, core)   # the band's counts: the worker's refresh_counts


class Verified(NamedTuple):
    selection: Any
    evidence: Any
    pending: Any
    regressing: dict[str, Any]
    open_regressions: list[str]
    masked: list[Any]
    open_masked: list[Any]
    not_run: list[str]
    unselected: bool


def _verification(ctx: HookContext, core: Any, verify: Any, index: Any, all_statuses: Any,
                  touched_ids: Sequence[str], changed: Sequence[str], turn_start: float,
                  asked: dict[str, Any], skipped: list[str]) -> Verified:
    """What the turn's tests say: the selection, its evidence, the full run still pending, the
    regressions (recorded or seen now) and those still to ask, the acceptance tests hidden by a
    test change, the covering tests not run and whether the budget cut the selection."""
    # trigger 3 first (R3, R5): the regressions this turn's runs recorded come from the
    # evidence index alone, before any step a budget can cut (no test map needed)
    recorded = turn_regressions(verify, turn_start)
    selection = evidence = pending = None
    if verify is not None:
        if time_left_s(ctx) <= 0:   # the soft budget or the room under the hard limit is gone
            skipped.append("covering tests")
        else:
            selection = verify.select(changed,
                                      budget_s=float(core.config.verify.turn_budget_s))
            evidence = dict(verify.evidence(selection.nodes)) if selection.nodes else {}
            pending = verify.full_pending()
    # trigger 3: regressions (R3), asked once per failing run
    regressing = {n: e for n, e in (evidence or {}).items() if e.regression}
    regressing.update({n: e for n, e in (recorded or {}).items() if n not in regressing})
    regressing = {n: e for n, e in regressing.items() if test_exists(core.root, n)}
    open_regressions = [n for n in sorted(regressing)
                        if asked.get(f"regression:{n}") != (regressing[n].last_run or "?")]
    # trigger 3 as well: a regression of a confirmed example hidden by changing its test
    masked = masked_acceptance(core, verify, index, all_statuses, touched_ids, changed)
    open_masked = [m for m in masked
                   if asked.get(f"masked:{m['node']}") != str(m.get("masked_by") or "?")]
    not_run = [n for n, e in (evidence or {}).items() if e.state in ("none", "stale")]
    # R5: a turn that changed code always gets its covering tests run; when the budget cut
    # the selection, the agent's own `iaso tests run --paths` selects them
    unselected = (verify is not None and selection is None
                  and any(is_code_path(core.config, p) for p in changed))
    return Verified(selection, evidence, pending, regressing, open_regressions, masked,
                    open_masked, not_run, unselected)


def handle(ctx: HookContext, *, verify: Any = LAZY, unjudged: Any = LAZY) -> HookOutput | None:
    """SR-375, SR-373: the inline work is what the next step needs (this turn's paths, their
    records, the covering selection, the regression check, the one next action, the status
    line); the rest goes to the background worker. ``unjudged`` is accepted for the callers
    and unused: fidelity is no longer checked at a turn's end."""
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
    skipped: list[str] = []
    git_timeout = min(GIT_TIMEOUT_S, max(ctx.deadline.remaining_s(), 0.05))
    job = GitStatusJob(ctx.root, git_timeout) if turn_start > 0 else None
    from iaso.api import open_core
    from iaso.hosts.claude_code.snapshot import tests_state, write_turn_fields
    from iaso.understand.summary import queue_after_stop

    # first, so no cut loses it: the confirmations, the upkeep and the jobs (SR-375)
    queue_after_stop(ctx.root, ctx.session_id, turn, ctx.data.get("transcript_path"))
    ctx.mark("queue background")
    core = open_core(ctx.root)
    core.index()  # read while git status runs; both turn paths need it
    ctx.mark("record index")
    changed = changed_paths(ctx.root, session_dir / "touched.txt", turn_start, git_timeout,
                            skipped, job)
    ctx.mark("changed paths")
    if not changed:
        if not active:
            queue_notes(ctx, early_asks(ctx, core, turn))
        return (None if active else _ask_block(ctx, core)) or _unchanged(ctx, core, turn,
                                                                         skipped)
    index = core.index()
    by_path = core.records_for_paths(changed)
    touched_ids = sorted({i for ids in by_path.values() for i in ids if i in index})
    changed_set = set(changed)
    edited_ids = [i for i in touched_ids if index[i].path in changed_set]
    statuses = core.status(touched_ids)   # SR-375: no link state of an untouched record
    stated_ids = [i for i in edited_ids if statuses[i].confirmation != "confirmed"]
    write_stated(ctx, turn, index, stated_ids)   # nothing drawn: a bare "ok" confirms nothing
    from iaso.present.cards import session_intent
    from iaso.trace import untraced_paths

    intent_summary = session_intent(core, index, touched_ids, session_dir)
    present = getattr(core.config, "present", None)
    # the status line first: a later cut must not leave it on an older turn
    write_turn_fields(ctx.root, present=present, tests="unknown", failing=(), regressions=(),
                      skipped=None, intent_summary=intent_summary)
    ctx.mark("records")
    # work no requirement owns escaped the translation chain (R1): the next prompt hook
    # delivers the note
    queued = untraced_paths(core, changed)   # the emitter tells each path once (sp5 3)
    if queued:
        write_json_atomic(session_dir / "untraced.json",
                          {"paths": queued, "prompt_digest": turn.get("prompt_digest")})
    ctx.mark("untraced")
    verify = verify_api(core, verify)
    v = _verification(ctx, core, verify, index, statuses, touched_ids, changed,
                      turn_start, asked, skipped)
    ctx.mark("covering tests")
    tests, failing, regressions = tests_state(v.evidence)
    write_turn_fields(ctx.root, present=present, tests=tests, failing=failing,
                      regressions=regressions,
                      deferred=len(v.selection.deferred) if v.selection else 0,
                      full_pending=bool(v.pending and v.pending.pending),
                      full_pending_reasons=tuple(v.pending.reasons) if v.pending else (),
                      ask=len(v.regressing) + len(v.masked),
                      skipped=", ".join(skipped) or None, intent_summary=intent_summary)
    # sp6 9.2, 9.4, R17: publish this worktree's changes, keep its intent in flight in step,
    # and the overlap lines of the records this turn touched (each once per other version)
    from iaso.awareness.turn import at_stop

    aware = at_stop(core, changed, touched_ids, capped_deadline(ctx))
    ctx.mark("awareness")
    out, stale_notes = _next_action(ctx, core, index, turn, turn_path, active,
                                    v, changed, asked, queued, turn_start)
    ctx.mark("next action")
    queue_notes(ctx, [*stale_notes, *(line.text for line in aware),
                      *([] if active else early_asks(ctx, core, turn)),
                      *([skip_notice(skipped)] if skipped else [])])
    out = out if out is not None else owner_output(ctx, core)
    ctx.mark("owner line")
    return out


def _behaviour(core: Any, index: Mapping[str, Any], nodes: Iterable[str],
               masked: Sequence[Mapping[str, Any]]) -> list[str]:
    """The confirmed requirements the regressing tests verify, by title (SR-373 EX-5)."""
    nodes = set(nodes)
    test_files = {n.split("::", 1)[0] for n in nodes}
    verifying = [r.id for r in index.values() if r.kind == "requirement" and {
        link.target.test or link.target.path or "" for link in r.links
        if link.kind == "verified_by"} & (nodes | test_files)]
    titles: dict[str, None] = {}
    for record_id, status in core.status(verifying).items():
        if status.confirmation == "confirmed":
            titles.setdefault(index[record_id].title, None)
    for item in masked:
        for record_id in item.get("requirements") or {}:
            if record_id in index:
                titles.setdefault(index[record_id].title, None)
    return list(titles)


def _next_action(ctx: HookContext, core: Any, index: Any, turn: Mapping[str, Any], turn_path: Path, active: bool, v: Verified,
                 changed: Sequence[str], asked: dict[str, Any],
                 queued: Sequence[str], turn_start: float
                 ) -> tuple[HookOutput | None, list[str]]:
    """SR-373: ``(the block naming the one next action, or None; the stale notes to queue)``.

    The action is the first of: a regression > the covering tests lacking a fresh run > a
    file no requirement owns (never a block: its note waits for the next prompt, R1) > the
    links this turn moved > the judge's questions. Each is said
    once per session per state (``iaso.present.delta``); one already said gives way to the
    next. A stop that already followed a block repeats only the stale hold (SR-111)."""
    if active:
        stale_reasons, notes = stale_hold(ctx, core, index, turn, turn_start)
        return (HookOutput(block_reason="\n".join(stale_reasons)) if stale_reasons
                else None), notes
    from iaso.present.delta import Line, open_emitter

    emitter = open_emitter(ctx, "stop", config=core.config)
    regressions = [Line(_regression_line(n, v.regressing[n]), subject=f"regression:{n}",
                        state=v.regressing[n].last_run or "?", must=True)
                   for n in v.open_regressions]
    regressions += [Line(_masked_line(index, m), subject=f"masked:{m['node']}",
                         state=str(m.get("masked_by") or "?"), must=True)
                    for m in v.open_masked]
    reasons = emitter.add(regressions)
    owner = ""
    if reasons:
        for n in v.open_regressions:
            asked[f"regression:{n}"] = v.regressing[n].last_run or "?"
        for m in v.open_masked:
            asked[f"masked:{m['node']}"] = str(m.get("masked_by") or "?")
        titles = _behaviour(core, index, v.open_regressions, v.open_masked)
        if titles:
            owner = ("iaso: regression: " + "; ".join(f"'{t}'" for t in titles[:2])
                     + (f" and {len(titles) - 2} more" if len(titles) > 2 else "")
                     + " worked before and now fails")
    if not reasons and (v.not_run or v.unselected):
        reasons = emitter.add([Line(tests_instruction(changed,
                                                      float(core.config.verify.turn_budget_s)),
                                    subject="tests", must=True, per_turn=True)])
    if not reasons and queued:
        emitter.close()
        return None, []   # R1: never a block; the note waits for the next prompt hook
    notes: list[str] = []
    if not reasons:
        reasons, notes = stale_hold(ctx, core, index, turn, turn_start)
    if not reasons:
        reasons = emitter.add(_questions_line(core, ctx.session_id))
    emitter.close()
    if not reasons:
        return None, notes
    write_json_atomic(turn_path, {**turn, "asked": asked})
    line = ""
    if owner:
        try:
            from iaso.understand.summary import owner_line

            line = owner_line(core, ctx.session_id, regression=owner)
        except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
            line = ""
    return HookOutput(block_reason="\n".join(reasons), system_message=line), notes


ASK_WAITING = ("iaso: {n} judge question{s} wait for the owner: run `iaso clarify --wait --json` "
               "and ask them now with the question tool, before the turn ends (reword, merge, "
               "push back; never drop one).")


def _questions_line(core: Any, session: str) -> list[Any]:
    """SR-361 EX-5: judge questions raised since the agent last asked reach it before it stops,
    once per set of questions; the band alone reaches nobody. Never fails the stop."""
    try:
        from iaso.present.delta import Line
        from iaso.understand import judge

        keys = sorted(str(q.get("key")) for q in judge.to_ask(core, session))
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return []
    if not keys:
        return []
    state = hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()[:16]
    return [Line(ASK_WAITING.format(n=len(keys), s="s" if len(keys) > 1 else ""),
                 subject="judge-questions", state=state, must=True)]


def _ask_block(ctx: HookContext, core: Any) -> HookOutput | None:
    """A turn with no edit still stops on judge questions nobody asked (SR-361 EX-5)."""
    lines = _questions_line(core, ctx.session_id)
    if not lines:
        return None
    from iaso.present.delta import open_emitter

    emitter = open_emitter(ctx, "stop", config=core.config)
    reasons = emitter.add(lines)
    emitter.close()
    return HookOutput(block_reason="\n".join(reasons)) if reasons else None


def owner_output(ctx: HookContext, core: Any) -> HookOutput | None:
    """SR-373: the owner's one plain line when something needs them, else nothing."""
    try:
        from iaso.understand.summary import owner_line

        line = owner_line(core, ctx.session_id)
        if line:   # SR-295 EX-1: the merge that waits reaches the agent, to be asked
            from iaso.mergedriver.conflicts import open_conflicts
            from iaso.understand.summary import ASK_OWNER

            titles = "; ".join(f'"{c.title}"' for c in open_conflicts(core))
            queue_notes(ctx, [f"{ASK_OWNER} {titles}"] if titles else [])
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        line = ""
    return HookOutput(system_message=line) if line else None


def early_conflicts(ctx: HookContext, core: Any, turn: Mapping[str, Any]) -> list[Any]:
    """The early intent conflicts ``capture``, ``clarify`` or this stop's claim asked for this
    turn, less the records an open merge conflict already asks about. Never fails the stop."""
    if not turn.get("turn_start"):
        return []
    try:
        from iaso.awareness.early import turn_conflicts
        from iaso.mergedriver.conflicts import open_conflicts

        merged = {c.record for c in open_conflicts(core)}
        start = _iso(float(turn["turn_start"]))
        return [c for c in turn_conflicts(ctx.session_dir, start) if c.record not in merged]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return []


def early_asks(ctx: HookContext, core: Any, turn: Mapping[str, Any]) -> list[str]:
    """SR-259, SR-295: each early conflict of this turn reaches the agent, both versions by
    branch, with the instruction to ask the owner (the card that showed it is gone,
    DEC-384)."""
    from iaso.awareness.early import question
    from iaso.understand.summary import ASK_OWNER

    return [f"{ASK_OWNER} {question(c)}" for c in early_conflicts(ctx, core, turn)]


def queue_notes(ctx: HookContext, notes: Sequence[str]) -> None:
    """SR-173: a stop that blocks nothing cannot tell the agent its warnings, so they wait for
    the next prompt hook (``prompt.agent_notes``), panel or not. Never fails the stop."""
    if notes:
        try:
            path = ctx.session_dir / ctx.session_id / "agent_notes.json"
            kept = read_json(path)      # the worker's waiting lines (SR-185) wait there too
            write_json_atomic(path, [*(kept if isinstance(kept, list) else []), *notes])
        except OSError:
            pass


def note_skipped(root: Path, skipped: Sequence[str]) -> None:
    """A step skipped by the budget is named in the status line (``status.json``'s
    ``skipped``), never in the owner's text (cards only)."""
    path = state_dir(Path(root)) / "session" / "status.json"
    data = read_json(path)
    if not isinstance(data, dict):
        data = {}
    data["skipped"] = ", ".join(skipped)
    try:
        write_json_atomic(path, data)
    except OSError:
        pass


def question_released(core: Any, session: str, rows: Sequence[Any], index: Mapping[str, Any],
                      held: int) -> list[str]:
    """The hold gave up on ``rows``: an owner question per link (the owner decides), and the
    note saying the hold ended, per link."""
    from iaso import stale
    from iaso.present.owner_text import STALE_HOLD_ENDED

    notes = []
    for row in rows:
        title = index[row.record].title if row.record in index else row.record
        other = index[row.what].title if row.what in index else ""
        stale.ask_owner(core, session, **stale.default_question(row, title, other))
        notes.append(STALE_HOLD_ENDED.format(n=held, title=title))
    return notes


def stale_hold(ctx: HookContext, core: Any, index: Mapping[str, Any],
               turn: Mapping[str, Any], turn_start: float) -> tuple[list[str], list[str]]:
    """SR-111 EX-3: ``(block reasons, summary lines)`` for the links this turn made stale.

    A stale link the turn caused (against the baseline the prompt hook wrote) that no open
    question holds keeps the turn open, naming it, up to ``hooks.stale_holds_max`` consecutive holds;
    then the turn is let go with an owner question per link. The links stale before the turn are
    listed to the agent once per session and never block: in the block when there is one,
    else queued for the next prompt hook (``stale.take_before``). Without a baseline of this
    turn nothing is held. Never fails the stop."""
    try:
        from iaso import main_guard, stale

        if main_guard.main_checkout(Path(ctx.root) / str(ctx.data.get("cwd") or "."), ctx.root):
            return [], []   # SR-384: in main's checkout a stale link is resolved on a branch
        turn_id = turn.get("turn_id")
        state = stale.turn_state(core, ctx.session_id, str(turn_id) if turn_id else None)
        if not state.valid:
            return [], []
        before = []
        key = "before:" + ",".join(r.link for r in state.before)
        if state.before and not stale.listed(ctx.root, ctx.session_id, key):
            before = [stale.before_line(state.before)]
        open_rows = stale.unresolved(core, ctx.session_id, state)
        waiting: list[str] = []
        if open_rows:   # SR-175: drift is checked for coverage and repinned before any hold
            no_judge: set[str] = set()
            # SR-310: its test runs and judge calls keep to the hook's time (hook-stop-e98405d1)
            waiting = stale.settle_drift(core, ctx.session_id, open_rows, no_judge,
                                         budget_s=time_left_s(ctx))
            state = stale.turn_state(core, ctx.session_id, str(turn_id) if turn_id else None)
            # SR-174, DEC-060: a check that waits for the judge does not hold the turn
            open_rows = [r for r in stale.unresolved(core, ctx.session_id, state)
                         if r.record not in no_judge]
        stale.ask_lost_tests(core, ctx.session_id)
        held = stale.hold_count(ctx.root, ctx.session_id, str(turn_id))
        limit = int(core.config.hooks.stale_holds_max)
        if ctx.extra.get("host"):
            limit = min(limit, 1)  # the host-neutral path blocks at most once per turn
        if before and open_rows and held < limit:
            stale.once_per_session(ctx.root, ctx.session_id, key)  # the block tells the agent
        elif before:
            stale.queue_before(ctx.root, ctx.session_id, key, before[0])  # the next prompt does
            before = []
        if not open_rows:
            if held:
                stale.set_hold_count(ctx.root, ctx.session_id, str(turn_id), 0)
            return [], waiting
        if held < limit:
            stale.set_hold_count(ctx.root, ctx.session_id, str(turn_id), held + 1)
            return [*waiting, *stale.hold_lines(open_rows, held + 1, limit), *before], []
        return [], [*waiting, *question_released(core, ctx.session_id, open_rows, index, held)]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return [], []


def conflict_entries(core: Any) -> list[dict[str, Any]]:
    """The stated entries of the open intent conflicts, whose cards every turn end draws
    (the owner's relayed words may choose among them, DEC-051). Never fails the stop."""
    try:
        from iaso.mergedriver.conflicts import open_conflicts, stated_entries

        return stated_entries(core, [c.ic for c in open_conflicts(core)])
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return []


def test_exists(root: Path | str, node: str) -> bool:
    """A recorded test still defined in its file: a failure recorded for a test since removed
    or renamed (its file gone, or no ``def`` of its name left) is not a regression."""
    path, _, rest = node.partition("::")
    name = re.sub(r"\[.*\]$", "", rest.split("::")[-1]) if rest else ""
    try:
        text = (Path(root) / path).read_text(encoding="utf-8")
    except OSError:
        return False
    return not name or re.search(rf"\bdef {re.escape(name)}\b", text) is not None


def turn_regressions(verify: Any, turn_start: float) -> dict[str, Any] | None:
    """The regressions this turn's test runs recorded (``VerifyAPI.recorded_regressions``
    since the turn started), or None when they could not be read (no VERIFY, no turn start,
    or a VerifyAPI without the method)."""
    if verify is None or not turn_start or not hasattr(verify, "recorded_regressions"):
        return None
    try:
        return dict(verify.recorded_regressions(_iso(max(turn_start - 1.0, 0.0))))
    except Exception:  # noqa: BLE001 - a lane failure degrades, never breaks the stop
        return None


def _quote(path: str) -> str:
    return f'"{path}"' if any(c.isspace() for c in path) else path


def tests_instruction(changed: Sequence[str], budget: float) -> str:
    """The test command for this turn: ``--paths`` names the turn's own changed paths, so
    other uncommitted work in the tree cannot crowd its covering tests out of the budget
    (``--changed`` covers every uncommitted path); ``--changed`` only for a long list."""
    if 0 < len(changed) <= MAX_INSTRUCTION_PATHS:
        command = "iaso tests run --paths " + " ".join(_quote(p) for p in changed)
        scope = "covering tests of this turn"
    else:
        command, scope = "iaso tests run --changed", "covering tests"
    return f"iaso: run '{command}' ({scope}, budget {budget:g} s), then finish your reply."


def skip_notice(skipped: Sequence[str]) -> str:
    """The notice naming the steps that would have started past the deadline (spec 10)."""
    return "iaso: check skipped (budget): " + ", ".join(skipped)


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, unjudged: Any = LAZY) -> int:
    from iaso.mod.handshake import deliver

    # with iaso's panel active, the owner's part goes to present.json, not a systemMessage
    def answer(ctx: HookContext) -> HookOutput | None:
        out = deliver(ctx, handle(ctx, verify=verify, unjudged=unjudged))
        ctx.mark("panel")
        return out

    return run_hook("stop", answer,
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("stop"),
                    json_output=True, watchdog=watchdog, start=start, grace_s=STOP_GRACE_S)
