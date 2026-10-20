"""Stop: covering tests within the budget, the three triggers, then the cards (spec 6.4;
sp7-realign-sp8 C7, slice 3).

1. This turn's changed paths: the session's ``touched.txt`` plus every path of one
   ``git status`` call whose mtime is at or after the turn start.
2. Their records (``CoreAPI.records_for_paths``), the link states of those records only, the
   covering selection (``VerifyAPI.select``) and its evidence.
3. The read-back comes first (R1): the cards drawn from the record states alone (a changed
   acceptance test) are kept (``HookContext.keep``) before any evidence step, so a budget cut,
   an error or the watchdog still shows them. Then the covering tests and fidelity. Write
   ``status.json`` (the status line: the status card lives there, never in the owner's text)
   and the stated set (``stated.json``): a stated record is ``shown`` only when a card drew it
   in full on plumb's panel (without it the cards reach the agent only, SR-295).
4. At most one block per turn, never when the host says ``stop_hook_active``: covering tests
   without fresh evidence (the agent runs ``plumb tests run --paths <this turn's paths>`` in
   its turn; the hook never runs pytest) and a regression (trigger 3, R3: a node that passed
   with recorded evidence and now fails; once per failing run). A new test that starts red is
   "not yet passing" and never asks. The block's lines go through the one emitter
   (``plumb.present.delta``): each once per session per state, within
   ``hooks.stop_tokens``; the covering-tests instruction and the skipped-check notice are
   about this turn (``per_turn``), so every turn whose covering tests lack fresh evidence
   blocks once, whatever the prompt's words. The block is for the agent; the owner sees none
   of it.
5. Otherwise ``StopParts`` (what the owner's words confirmed, then the cards) go to the
   agent as text, queued for the next prompt (SR-266). The stop hook builds the cards of its
   own facts (``plumb.understand.cards``): a regression, a changed acceptance test, a merge
   conflict, an early conflict; the summary of the understanding layer draws them with its own
   and the stale-link and drift cards, each in full, those only the owner can settle tagged
   for the agent to ask with the question tool (SR-295). The owner's text is at most one plumb
   line (``summary.owner_line``, SR-265); a turn with nothing for the owner shows nothing. A
   decision is never asked here, as a card or in the agent's words (INT-037).

The deadline is checked before a step starts, never after it ends (spec 10): a step that
would start past the soft budget is skipped and named in the status line, and results already
computed are always used (the stated set, the snapshot, the block and the cards). The record
states and the read-back are never skipped by the soft budget: only the watchdog's hard limit
bounds them, and it prints whatever was kept.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple, TextIO

from plumb.hosts.claude_code.hookio import (
    HookContext,
    HookOutput,
    hook_budget,
    read_json,
    run_hook,
    write_json_atomic,
)
from plumb.hosts.claude_code.providers import LAZY, unjudged_fn, verify_api
from plumb.trace import is_code_path

IGNORED_PREFIXES = (".plumb/session/", ".plumb/cache/", ".plumb/log/", ".plumb/view/",
                    ".git/")
IGNORED_FILES = (".plumb/test_map.txt",)
GIT_TIMEOUT_S = 5.0  # a slice of the soft budget: under load git status alone can take 0.6 s
STOP_GRACE_S = 1.0  # past the hard limit, only while the read-back is not yet kept (R1)
GIT_SKIPPED = "change detection (git status)"
MAX_INSTRUCTION_PATHS = 8


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
    return _clip(f"plumb: regression hidden: {item['node']} passed in run "
                 f"{item.get('passed_in') or '?'}, then failed, and passes now only because "
                 f"the test itself was changed. It verifies {'; '.join(parts)}, which the "
                 "owner confirmed. Tell the owner, with a read-back of the code and test "
                 "change, and ask how to proceed; a test is not rewritten to pass.", 600)


def _regression_line(node: str, evidence: Any) -> str:
    note = " (test source changed since the pass)" if evidence.test_changed_since_pass else ""
    run = f" (last run {evidence.last_run})" if evidence.last_run else ""
    return (f"plumb: regression: {node} passed in an earlier run and now fails{note}{run}. "
            "Tell the owner, with a read-back, and ask how to proceed.")


def write_stated(ctx: HookContext, turn: Mapping[str, Any], index: Mapping[str, Any],
                 stated_ids: Sequence[str], shown: Iterable[str] = (), *,
                 early: Sequence[Mapping[str, Any]] = (),
                 conflicts: Sequence[Mapping[str, Any]] = ()) -> None:
    """The stated set of this reply: what a bare affirmation of the owner may confirm.

    The one writer of ``stated.json``, so it holds the guarantee "``shown`` only when the
    owner sees the card" for every host: a drawn card reaches the owner only while plumb's
    panel is active (``present.json``), otherwise the agent's channel alone (SR-295) (``ctx.extra["display"]``, set by
    ``hosts.neutral.handle_event``): ``owner`` (the host shows ``owner_lines``) keeps
    ``shown``; ``unseen`` (the host could not show them) writes no record as shown;
    ``status`` (a status refresh, e.g. Codex's ``notify``) leaves the stated set of the reply
    the owner actually answers untouched."""
    from plumb.normalize import utc_now

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
        from plumb.mod.handshake import active

        return active(ctx.root, ctx.session_id, float(turn.get("turn_start") or 0))
    except Exception:  # noqa: BLE001 - unknown means unseen: a bare "ok" confirms nothing
        return False


def _unchanged(ctx: HookContext, core: Any, turn: Mapping[str, Any],
               skipped: Sequence[str]) -> HookOutput | None:
    """A turn with no edit: the cards plumb conflicts, capture or the clarify read-back asked
    for and what the owner's words confirmed need none (R17: asked at once)."""
    if skipped:  # a timed-out git status is no evidence of a turn without changes
        note_skipped(ctx.root, skipped)
    fresh, early = owner_cards(ctx, core, turn)
    shown: dict[str, str] = {}
    before = _drawn_before(core, ctx.session_id)
    text = understand_parts(ctx, core, turn, fresh=fresh, shown=shown)
    write_stated(ctx, turn, {}, [], early=early, conflicts=conflict_entries(core))
    from plumb.hosts.claude_code.snapshot import refresh_judge_count

    try:
        refresh_judge_count(core)
    except Exception:  # noqa: BLE001 - the band's count is advisory; the turn end goes on
        pass
    return owner_output(ctx, core, text, before)


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
        if ctx.deadline.expired():
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
    # the selection, the agent's own `plumb tests run --paths` selects them
    unselected = (verify is not None and selection is None
                  and any(is_code_path(core.config, p) for p in changed))
    return Verified(selection, evidence, pending, regressing, open_regressions, masked,
                    open_masked, not_run, unselected)


def _unjudged(ctx: HookContext, core: Any, unjudged: Any, touched_ids: Sequence[str],
              index: Any, skipped: list[str]) -> tuple[Any, ...]:
    """The touched requirements whose fidelity is not judged yet (advisory only)."""
    requirement_ids = [i for i in touched_ids if index[i].kind == "requirement"]
    if unjudged is None or not requirement_ids:
        return ()
    if ctx.deadline.expired():
        skipped.append("fidelity")
        return ()
    try:
        return tuple(unjudged(core, requirement_ids))
    except Exception:  # noqa: BLE001 - advisory only
        return ()


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
    skipped: list[str] = []
    git_timeout = min(GIT_TIMEOUT_S, max(ctx.deadline.remaining_s(), 0.05))
    job = GitStatusJob(ctx.root, git_timeout) if turn_start > 0 else None
    from plumb.api import open_core
    from plumb.hosts.claude_code.snapshot import build_snapshot, write_snapshot

    core = open_core(ctx.root)
    core.index()  # read while git status runs; both turn paths need it
    changed = changed_paths(ctx.root, session_dir / "touched.txt", turn_start, git_timeout,
                            skipped, job)
    if not changed:
        return _unchanged(ctx, core, turn, skipped)
    # no soft-budget check before the read-back (R1): only the watchdog bounds it
    index = core.index()
    by_path = core.records_for_paths(changed)
    touched_ids = sorted({i for ids in by_path.values() for i in ids if i in index})
    changed_set = set(changed)
    edited_ids = [i for i in touched_ids if index[i].path in changed_set]
    all_statuses = core.status()
    from plumb.trace import untraced_paths

    # work no requirement owns escaped the translation chain: the agent is told to read it
    # back and record a proposed SR (non-blocking, R1)
    untraced = untraced_paths(core, changed)
    told_raw = turn.get("untraced_told")
    told = {str(p) for p in told_raw} if isinstance(told_raw, list) else set()

    stated_ids = [i for i in edited_ids if all_statuses[i].confirmation != "confirmed"]
    from plumb.present.cards import session_intent

    intent_summary = session_intent(core, index, touched_ids, session_dir)
    # R1 first: the cards from the record states alone are kept before any evidence step, so
    # a cut (budget, error, watchdog) still shows them; kept before the stated set says
    # "shown", never after
    early_snapshot = build_snapshot(core, statuses=all_statuses, auto_approve="off",
                                    tests_summary=("unknown", (), ()),
                                    intent_summary=intent_summary)
    stamp = int(turn_start)
    test_cards = _early_state(ctx, core, index, turn, touched_ids, all_statuses, stated_ids,
                              early_snapshot, stamp)
    note_path = session_dir / "untraced.json"
    queued = [p for p in untraced if p not in told]
    if queued:  # delivered by the next prompt hook, so a cut after this still tells the agent
        write_json_atomic(note_path, {"paths": queued,
                                      "prompt_digest": turn.get("prompt_digest")})

    verify = verify_api(core, verify)
    v = _verification(ctx, core, verify, index, all_statuses, touched_ids, changed,
                      turn_start, asked, skipped)

    fidelity = _unjudged(ctx, core, unjudged_fn(unjudged), touched_ids, index, skipped)
    snapshot = build_snapshot(
        core, evidence=v.evidence, full_pending=v.pending, statuses=all_statuses,
        deferred=len(v.selection.deferred) if v.selection else 0, fidelity_unjudged=fidelity,
        ask=len(v.regressing) + len(v.masked), skipped=", ".join(skipped) or None,
        intent_summary=intent_summary)
    write_snapshot(ctx.root, snapshot, present=getattr(core.config, "present", None))
    # sp6 9.2, 9.4, R17: publish this worktree's changes, keep its intent in flight in step,
    # and the overlap lines of the records this turn touched (each once per other version)
    from plumb.awareness.turn import at_stop

    aware = at_stop(core, changed, touched_ids, ctx.deadline)
    stale_reasons, stale_notes = stale_hold(ctx, core, index, turn, turn_start)

    blocked = _block_reasons(ctx, core, index, turn, turn_path, active, v, changed, asked,
                             stated_ids, told, queued, note_path, skipped, aware,
                             stale_reasons)
    if blocked:
        return blocked
    queue_notes(ctx, [*stale_notes, *(line.text for line in aware),
                      *([skip_notice(skipped)] if skipped else [])])

    confirmed = [i for i in touched_ids if index[i].kind == "requirement"
                 and all_statuses[i].confirmation == "confirmed"]
    return _cards(ctx, core, index, turn, v, test_cards, stated_ids, stamp, confirmed)


def _early_state(ctx: HookContext, core: Any, index: Any, turn: Mapping[str, Any],
                 touched_ids: Sequence[str], all_statuses: Any, stated_ids: Sequence[str],
                 early_snapshot: Any, stamp: int) -> list[Any]:
    """Keep the test-changed cards, the stated set and the status line before any evidence step."""
    from plumb.hosts.claude_code.snapshot import write_snapshot
    from plumb.understand import cards as card_text

    # SR-030: a confirmed requirement whose acceptance test changed since the owner confirmed
    # it waits for the owner on its own card (never only in plumb status); it stays out of the
    # stated set, so a bare "ok" never confirms the new test (the card recommends putting the
    # test back)
    test_changed = [i for i in touched_ids if index[i].kind == "requirement"
                    and getattr(all_statuses.get(i), "changed_tests", ())]
    test_cards = [card_text.test_changed_card(index[i], all_statuses[i].changed_tests,
                                              turn=stamp) for i in test_changed]
    kept: dict[str, str] = {}
    ctx.keep(drawn_now(core, test_cards, kept))
    write_stated(ctx, turn, index, stated_ids, kept)
    # then the status line: a later cut (budget, watchdog) must not leave it on an older turn
    write_snapshot(ctx.root, early_snapshot, present=getattr(core.config, "present", None))
    return test_cards


def _block_reasons(ctx: HookContext, core: Any, index: Any, turn: Mapping[str, Any],
                   turn_path: Path, active: bool, v: Any, changed: Sequence[str],
                   asked: dict[str, Any], stated_ids: Sequence[str], told: set[str],
                   queued: Sequence[str], note_path: Path, skipped: Sequence[str],
                   aware: Sequence[str], stale_reasons: Sequence[str]) -> HookOutput | None:
    """The block that tells the agent what to do before it stops, or None to go on to cards."""
    from plumb.trace import trace_instruction

    if not active:
        from plumb.present.delta import Line, open_emitter

        # the agent's instructions go through the one emitter (sp5 3): each once per
        # session per state; the triggers and the tests instruction are never cut
        emitter = open_emitter(ctx, "stop", config=core.config)
        wanted: list[Line] = []
        if v.not_run or v.unselected:
            wanted.append(Line(tests_instruction(changed,
                                                 float(core.config.verify.turn_budget_s)),
                               subject="tests", must=True, per_turn=True))
        for n in v.open_regressions:
            wanted.append(Line(_regression_line(n, v.regressing[n]), subject=f"regression:{n}",
                               state=v.regressing[n].last_run or "?", must=True))
            asked[f"regression:{n}"] = v.regressing[n].last_run or "?"
        for m in v.open_masked:
            wanted.append(Line(_masked_line(index, m), subject=f"masked:{m['node']}",
                               state=str(m.get("masked_by") or "?"), must=True))
            asked[f"masked:{m['node']}"] = str(m.get("masked_by") or "?")
        reasons = emitter.add(wanted)
        if stale_reasons:  # SR-111: a link this turn made stale is still unresolved
            reasons = [*stale_reasons, *reasons]
        if reasons:
            if queued:  # the block tells the agent now; the next prompt need not repeat it
                new = [p for p in queued if emitter.is_new(f"untraced:{p}")]
                # oneshot: the note is removed below, so the budget must never cut it
                reasons += emitter.add([Line(trace_instruction(new, core=core),
                                             subject="untraced:" + "|".join(sorted(new)),
                                             marks=tuple(f"untraced:{p}" for p in new),
                                             oneshot=True)]
                                       if new else [])
                try:
                    note_path.unlink()
                except OSError:
                    pass
            if skipped:
                reasons += emitter.add([Line(skip_notice(skipped), per_turn=True)])
            reasons += emitter.add(aware)
            emitter.close()
            # a blocked stop shows the owner nothing: a bare "ok" confirms no record
            write_stated(ctx, turn, index, stated_ids)
            write_json_atomic(turn_path, {**turn, "asked": asked,
                                          "untraced_told": sorted(told | set(queued))})
            return HookOutput(block_reason="\n".join(reasons))
    elif stale_reasons:
        # the host says this stop already followed a block: only the stale hold repeats, up to
        # hooks.stale_holds_max times (stale.hold_count), so a turn is never held forever
        write_stated(ctx, turn, index, stated_ids)
        return HookOutput(block_reason="\n".join(stale_reasons))
    return None


def _cards(ctx: HookContext, core: Any, index: Any, turn: Mapping[str, Any], v: Any,
           test_cards: Sequence[Any], stated_ids: Sequence[str], stamp: int,
           confirmed: Sequence[str] = ()) -> HookOutput | None:
    """The cards, in full, to the agent; the owner's one line; the stated set."""
    passing = [n for n, e in (v.evidence or {}).items() if e.state in ("fresh-pass", "flaky-pass")]
    regression = regression_cards(index, v.regressing, v.masked, stamp)
    fresh, early = owner_cards(ctx, core, turn)
    shown: dict[str, str] = {}
    before = _drawn_before(core, ctx.session_id)
    text = understand_parts(ctx, core, turn, extra=[*regression, *test_cards], fresh=fresh,
                            passing=passing, shown=shown)
    write_stated(ctx, turn, index, stated_ids, shown, early=early,
                 conflicts=conflict_entries(core))
    return owner_output(ctx, core, text, before, touched=confirmed,
                        checks=(len(passing), len(v.evidence or {})))


def _drawn_before(core: Any, session: str) -> set[str]:
    try:
        from plumb.understand.summary import drawn_ids

        return drawn_ids(core.root, session)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return set()


def owner_output(ctx: HookContext, core: Any, text: Sequence[str], before: set[str], *,
                 touched: Sequence[str] = (), checks: tuple[int, int] = (0, 0)
                 ) -> HookOutput | None:
    """SR-266: everything for the agent goes to its channel as text, queued for the next
    prompt (the retired card setting named there, once per session); SR-265: the owner gets
    at most one plumb line, or nothing."""
    from plumb.config import CARD_RETIRED

    retired = [CARD_RETIRED] if getattr(getattr(core.config, "present", None), "card", "") else []
    queue_notes(ctx, [*retired, *text])
    try:
        from plumb.understand.summary import owner_line

        line = owner_line(core, ctx.session_id, before, touched=touched, checks=checks)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        line = ""
    return HookOutput(system_message=line) if line else None


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
    path = Path(root) / ".plumb" / "session" / "status.json"
    data = read_json(path)
    if not isinstance(data, dict):
        data = {}
    data["skipped"] = ", ".join(skipped)
    try:
        write_json_atomic(path, data)
    except OSError:
        pass


def drawn_now(core: Any, cards: Sequence[Any], shown: dict[str, str]) -> list[str]:
    """The cards built from the record states alone, drawn in full for the read-back the hook
    keeps before any evidence step (R1)."""
    from plumb.understand import fullcard

    out: list[str] = []
    try:
        for card in cards:
            out += fullcard.lines(fullcard.content(core, card))
            for question in card.questions:
                if question.record:
                    shown.setdefault(question.record, question.hash)
    except Exception:  # noqa: BLE001 - the full summary still draws them
        return out
    return out


def regression_cards(index: Mapping[str, Any], regressing: Mapping[str, Any],
                     masked: Sequence[Mapping[str, Any]], stamp: int) -> list[Any]:
    """SR-012 EX-2: a card per regression (and per regression a test change hid)."""
    from plumb.understand import cards as card_text

    out: list[Any] = []
    try:
        for node in sorted(regressing):
            found = regressing[node]
            out.append(card_text.regression_card(
                index, node, last_run=str(found.last_run or ""),
                test_changed=bool(getattr(found, "test_changed_since_pass", False)), turn=stamp))
        for item in masked:
            out.append(card_text.regression_card(index, str(item["node"]), hidden=True,
                                                 turn=stamp))
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return out
    return out


def card_released(root: Path, session: str, rows: Sequence[Any], index: Mapping[str, Any],
                  turn_start: float, held: int) -> list[str]:
    """The hold gave up on ``rows``: a stale card per link (the owner decides), and the note
    saying the hold ended, per link."""
    from plumb import stale
    from plumb.present.owner_text import STALE_HOLD_ENDED

    notes = []
    for row in rows:
        title = index[row.record].title if row.record in index else row.record
        other = index[row.what].title if row.what in index else ""
        stale.add_card(root, session, turn=int(turn_start),
                       **stale.default_card(row, title, other))
        notes.append(STALE_HOLD_ENDED.format(n=held, title=title))
    return notes


def stale_hold(ctx: HookContext, core: Any, index: Mapping[str, Any],
               turn: Mapping[str, Any], turn_start: float) -> tuple[list[str], list[str]]:
    """SR-111 EX-3: ``(block reasons, summary lines)`` for the links this turn made stale.

    A stale link the turn caused (against the baseline the prompt hook wrote) that no card
    holds keeps the turn open, naming it, up to ``hooks.stale_holds_max`` consecutive holds;
    then the turn is let go with a stale card per link. The links stale before the turn are
    listed to the agent once per session and never block: in the block when there is one,
    else queued for the next prompt hook (``stale.take_before``). Without a baseline of this
    turn nothing is held. Never fails the stop."""
    try:
        from plumb import stale

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
            waiting = stale.settle_drift(core, ctx.session_id, open_rows, no_judge)
            state = stale.turn_state(core, ctx.session_id, str(turn_id) if turn_id else None)
            # SR-174, DEC-060: a check that waits for the judge does not hold the turn
            open_rows = [r for r in stale.unresolved(core, ctx.session_id, state)
                         if r.record not in no_judge]
        stale.card_lost_tests(core, ctx.session_id)
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
            missing = stale.incomplete_cards(ctx.root, ctx.session_id)
            return [*waiting, *stale.hold_lines(open_rows, held + 1, limit, missing),
                    *before], []
        return [], [*waiting, *card_released(ctx.root, ctx.session_id, open_rows, index,
                                             turn_start, held)]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return [], []


def understand_parts(ctx: HookContext, core: Any, turn: Mapping[str, Any], *,
                     extra: Sequence[Any] = (), fresh: Sequence[Any] = (),
                     passing: Sequence[str] = (),
                     shown: dict[str, str] | None = None) -> list[str]:
    """SR-266: the agent's text at the end of a turn: what the owner confirmed by
    their words, then the cards (``understand.summary.stop_parts``, which
    draws every card in full and keeps ``extra`` open across turns while it holds). Never
    fails the stop."""
    try:
        from plumb.understand.summary import stop_parts

        parts = stop_parts(ctx, core, turn, extra=extra, fresh=fresh, passing=passing,
                           shown=shown)
        bag = getattr(ctx, "extra", None)
        if isinstance(bag, dict):
            bag["stop_parts"] = parts       # what present.json carries while the panel is on
        return [*parts.confirmations, *parts.cards]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return []


def conflict_entries(core: Any) -> list[dict[str, Any]]:
    """The stated entries of the open intent conflicts, whose cards every turn end draws
    (the owner's relayed words may choose among them, DEC-051). Never fails the stop."""
    try:
        from plumb.mergedriver.conflicts import open_conflicts, stated_entries

        return stated_entries(core, [c.ic for c in open_conflicts(core)])
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return []


def owner_cards(ctx: HookContext, core: Any, turn: Mapping[str, Any]
                ) -> tuple[list[Any], list[dict[str, Any]]]:
    """``(cards, early stated entries)``: a card per intent conflict a merge left (sp6 8.3),
    drawn at every turn end while it is open, and per early conflict ``capture`` or
    ``plumb clarify`` asked for this turn (R17); the early stated entries let the owner's
    next answer name the card. Never fails the stop."""
    from plumb.understand import cards as card_text

    index = core.index()
    stamp = int(float(turn.get("turn_start") or 0))
    out: list[Any] = []
    early: list[dict[str, Any]] = []
    found: list[Any] = []
    try:
        from plumb.mergedriver.conflicts import open_conflicts

        found = open_conflicts(core)
        out += [card_text.conflict_card(index, c, turn=stamp) for c in found]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        pass
    start = _iso(float(turn.get("turn_start") or 0)) if turn.get("turn_start") else ""
    try:
        from plumb.awareness.early import stated_entry, turn_conflicts

        merged = {c.record for c in found}   # the merge card asks for that record (EX-10)
        for conflict in turn_conflicts(ctx.session_dir, start):
            if conflict.record in merged:
                continue
            out.append(card_text.early_conflict_card(index, conflict, turn=stamp))
            early.append(stated_entry(conflict))
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        pass
    return out, early


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
        command = "plumb tests run --paths " + " ".join(_quote(p) for p in changed)
        scope = "covering tests of this turn"
    else:
        command, scope = "plumb tests run --changed", "covering tests"
    return f"plumb: run '{command}' ({scope}, budget {budget:g} s), then finish your reply."


def skip_notice(skipped: Sequence[str]) -> str:
    """The notice naming the steps that would have started past the deadline (spec 10)."""
    return "plumb: check skipped (budget): " + ", ".join(skipped)


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, unjudged: Any = LAZY) -> int:
    from plumb.mod.handshake import deliver

    # with plumb's panel active, the owner's part goes to present.json, not a systemMessage
    return run_hook("stop", lambda ctx: deliver(ctx, handle(ctx, verify=verify,
                                                            unjudged=unjudged)),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("stop"),
                    json_output=True, watchdog=watchdog, start=start, grace_s=STOP_GRACE_S)
