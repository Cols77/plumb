"""Stop: covering tests within the budget, the three triggers, then the cards (spec 6.4;
sp7-realign-sp8 C7, slice 3).

1. This turn's changed paths: the session's ``touched.txt`` plus every path of one
   ``git status`` call whose mtime is at or after the turn start.
2. Their records (``CoreAPI.records_for_paths``), the link states of those records only, the
   covering selection (``VerifyAPI.select``) and its evidence.
3. The read-back comes first (R1): the cards of the records this turn proposed (one per
   feature, DEC-029) are drawn from the record states alone and kept (``HookContext.keep``)
   before any evidence step, so a budget cut, an error or the watchdog still shows them. Then
   the covering tests and fidelity. Write ``status.json`` (the status line: the status card
   lives there, never in the owner's text) and the stated set (``stated.json``): a stated
   record is ``shown`` only when a card drew it in full.
4. At most one block per turn, never when the host says ``stop_hook_active``: covering tests
   without fresh evidence (the agent runs ``plumb tests run --paths <this turn's paths>`` in
   its turn; the hook never runs pytest), an unconfirmed decision that matters (trigger 2,
   once per hash) and a regression (trigger 3, R3: a node that passed with recorded
   evidence and now fails; once per failing run). A new test that starts red is "not yet
   passing" and never asks. The block's lines go through the one emitter
   (``plumb.present.delta``): each once per session per state, within
   ``hooks.stop_tokens``; the covering-tests instruction and the skipped-check notice are
   about this turn (``per_turn``), so every turn whose covering tests lack fresh evidence
   blocks once, whatever the prompt's words. The block is for the agent; the owner sees none
   of it.
5. Otherwise the owner's text is ``StopParts`` and nothing else (SR-012, SR-105 order): what
   the owner's words confirmed, the one settled line with Undo, then the cards. The stop hook
   builds the cards of its own facts (``plumb.understand.cards``): a regression, a decision
   that matters, a merge conflict, an early conflict, and the records this turn proposed
   that nothing settled, one card per feature; the summary of the understanding layer draws
   them with its own and the stale-link and drift cards, each in full (SR-116). No list of
   proposed records, no status card, no summary lines: a turn with nothing for the owner
   shows nothing. The records ``plumb confirm`` prepared this turn join the proposed cards.

The deadline is checked before a step starts, never after it ends (spec 10): a step that
would start past the soft budget is skipped and named in the status line, and results already
computed are always used (the stated set, the snapshot, the block and the cards). The record
states and the read-back are never skipped by the soft budget: only the watchdog's hard limit
bounds them, and it prints whatever was kept.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
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
from plumb.trace import is_code_path

IGNORED_PREFIXES = (".plumb/session/", ".plumb/cache/", ".plumb/log/", ".plumb/view/",
                    ".git/")
IGNORED_FILES = (".plumb/test_map.txt",)
GIT_TIMEOUT_S = 1.0  # most of the soft budget: under load git status alone can take 0.6 s
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


def _dec_question(record: Any) -> str:
    from plumb.awareness.answer import early_of

    early = early_of(record)
    if early is not None:  # R17: the early conflict card's own question and answers
        question = " ".join(str(record.fields.get("question") or record.title).split())
        return (f"plumb: {record.id} is unconfirmed and this work relies on it. Show the owner "
                f"the conflict card and ask: \"{question}\" They answer in the card's words "
                "(\"keep <branch>'s\", \"keep this one\" or \"both\"); relay those words as "
                f"the answer to {record.id}")
    chosen = str(record.fields.get("chosen") or "A").strip()
    alternatives = record.fields.get("alternatives") or []
    if isinstance(alternatives, str):
        alternatives = [alternatives]
    other = str(alternatives[0]).strip() if alternatives else "another reading"
    return (f"plumb: {record.id} is unconfirmed and this work relies on it. Ask the owner: "
            f"\"I assumed {chosen}; {other} also fits. Which one?\"")


def matters_decisions(index: Mapping[str, Any], statuses: Mapping[str, Any],
                      touched: Iterable[str]) -> list[str]:
    """Open DECs with ``matters: true`` that are touched or decide a touched record, earliest
    first: ``plumb.capture.clarify.open_decisions`` (unconfirmed and not superseded), the one
    rule the clarify queue and the escalation trigger share."""
    from plumb.awareness.answer import waiting_on_conflict
    from plumb.capture.clarify import open_decisions

    # an early decision whose record a merge left in conflict is asked by that merge card
    return [d for d in open_decisions(index, statuses, touched)
            if not waiting_on_conflict(index, d)]


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


@dataclass
class ConfirmView:
    """What ``plumb confirm`` prepared this turn and what this stop shows of it (sp5 6.3):
    the records a card drew in full (``id -> hash``); since slice 3 the records join the
    proposed cards and no group offer is drawn (``lines`` and ``shown_groups`` stay empty)."""

    records: list[dict[str, Any]] = field(default_factory=list)
    groups: list[dict[str, Any]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    shown: dict[str, str] = field(default_factory=dict)
    shown_groups: list[dict[str, Any]] = field(default_factory=list)


def confirm_carry(ctx: HookContext, turn: Mapping[str, Any]) -> ConfirmView:
    """The records and triage groups ``plumb confirm`` put in the stated set during this
    turn (``via: confirm``), nothing rendered yet."""
    previous = read_json(ctx.session_dir / "stated.json")
    if not isinstance(previous, dict):
        return ConfirmView()
    start = _iso(float(turn.get("turn_start") or 0)) if turn.get("turn_start") else ""
    if not start or str(previous.get("at") or "") < start:
        return ConfirmView()
    records = [dict(item) for item in previous.get("records") or []
               if isinstance(item, dict) and item.get("via") == "confirm" and item.get("id")]
    groups = [dict(item) for item in previous.get("confirm_groups") or []
              if isinstance(item, dict) and item.get("group")]
    # SR-012, DEC-029: no group offer is drawn any more, so the records of the triage group
    # plumb confirm prepared join the prepared records and reach the owner on their cards
    known = {str(r["id"]) for r in records}
    for group in groups:
        for item in group.get("records") or []:
            if isinstance(item, dict) and item.get("id") and str(item["id"]) not in known:
                known.add(str(item["id"]))
                records.append({"id": str(item["id"]), "hash": item.get("hash"),
                                "shown": False, "via": "confirm"})
    return ConfirmView(records=records, groups=groups)


_ASKED = re.compile(
    r"^[ \t>#*_-]*Question[ \t]*\([ \t]*\**(DEC-\d+)\**[ \t]*\)", re.MULTILINE)


def reply_text(ctx: HookContext) -> str:
    """The agent's last reply as the host gave it: ``last_assistant_message``, else the last
    assistant entry of the transcript. Empty when neither is available."""
    text = ctx.data.get("last_assistant_message")
    if isinstance(text, str):
        return text
    path = ctx.data.get("transcript_path")
    if not isinstance(path, str) or not path:
        return ""
    last = ""
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                message = entry.get("message") if isinstance(entry, dict) else None
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    last = content
                elif isinstance(content, list):
                    last = "\n".join(str(b.get("text")) for b in content
                                     if isinstance(b, dict) and b.get("type") == "text")
    except OSError:
        return ""
    return last


def asked_decisions(ctx: HookContext) -> dict[str, str]:
    """Decisions the reply asked as plain text, "Question (DEC-026): ..." at a line start.

    A decision named in passing ("see DEC-002") is not asked. Only a decision that exists is
    returned, with its current hash."""
    found = list(dict.fromkeys(_ASKED.findall(reply_text(ctx))))
    if not found:
        return {}
    from plumb.api import open_core

    known = open_core(ctx.root).index()
    return {i: known[i].hash for i in found if i in known}


def write_stated(ctx: HookContext, turn: Mapping[str, Any], index: Mapping[str, Any],
                 stated_ids: Sequence[str], shown: Iterable[str] = (), *,
                 group: Mapping[str, Any] | None = None, offer: Sequence[str] = (),
                 message: str = "", confirm: ConfirmView | None = None,
                 conflicts: Sequence[Mapping[str, Any]] = (),
                 early: Sequence[Mapping[str, Any]] = ()) -> None:
    """The stated set of this reply: what a bare affirmation of the owner may confirm.

    The records and groups ``plumb confirm`` prepared this turn stay in it (``via:
    confirm``); they are shown, and a group relayable (``groups``), only as ``confirm``
    rendered them (``confirm_view``). Without ``confirm`` (a blocked stop shows the owner
    nothing) they are kept unshown for the turn's last stop. ``group`` is the triage offer
    of this turn's own records (``plumb relay --group``), pinned only when its ``offer``
    lines are in ``message``, the text the owner is shown (R2, DEC-017): a group the
    owner never saw (``present.card: off`` hides the offer) is never relayable.

    The one writer of ``stated.json``, so it holds the guarantee "``shown`` only when the
    owner sees the summary" for every host (``ctx.extra["display"]``, set by
    ``hosts.neutral.handle_event``): ``owner`` (the host shows ``owner_lines``) keeps
    ``shown``; ``unseen`` (the host could not show them) writes no record or group as shown;
    ``status`` (a status refresh, e.g. Codex's ``notify``) leaves the stated set of the reply
    the owner actually answers untouched."""
    from plumb.normalize import utc_now

    display = ctx.extra.get("display", "owner")
    if display == "status":
        return
    seen = display == "owner"
    carry = confirm if confirm is not None else confirm_carry(ctx, turn)
    rendered = confirm.shown if confirm is not None and seen else {}
    shown = set(shown) if seen else set()
    records = [{"id": i, "hash": index[i].hash, "shown": i in shown} for i in stated_ids]
    by_id = {r["id"]: r for r in records}
    if seen:  # a question asked as plain text is the whole of what the owner answers
        for record_id, current in asked_decisions(ctx).items():
            if record_id not in by_id:
                by_id[record_id] = {"id": record_id, "hash": current, "shown": True}
                records.append(by_id[record_id])
    for item in carry.records:
        record_id = item["id"]
        if record_id in rendered:
            if record_id in by_id:  # still prepared by plumb confirm for a later stop
                by_id[record_id].update(hash=rendered[record_id], shown=True, via="confirm")
                continue
            item = {**item, "hash": rendered[record_id], "shown": True}
        elif record_id in by_id:
            by_id[record_id]["via"] = "confirm"
            continue
        else:
            item = {**item, "shown": False}
        by_id[record_id] = item
        records.append(item)
    data: dict[str, Any] = {"at": utc_now(), "session": ctx.session_id,
                            "reply_after_prompt": turn.get("prompt_digest"),
                            "records": records}
    groups = list(confirm.shown_groups) if confirm is not None and seen else []
    if seen and group is not None and not carry.groups and offered(offer, message):
        groups.append(dict(group))
    if groups:
        data["groups"] = groups
    if carry.groups:
        data["confirm_groups"] = carry.groups
    if seen and conflicts:  # sp6 8.4: the conflict cards this reply showed the owner
        data["conflicts"] = [dict(c) for c in conflicts]
    if seen and early:  # R17: the early conflict cards this reply showed the owner
        data["early"] = [dict(c) for c in early]
    write_json_atomic(ctx.session_dir / "stated.json", data)


def offered(offer: Sequence[str], message: str) -> bool:
    """True when every offer line is a line of ``message`` (what reached the owner)."""
    shown = set(message.splitlines())
    return bool(offer) and all(line in shown for line in offer)


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
    from plumb.understand import cards as card_text

    core = open_core(ctx.root)
    core.index()  # read while git status runs; both turn paths need it
    changed = changed_paths(ctx.root, session_dir / "touched.txt", turn_start, git_timeout,
                            skipped, job)
    # what plumb confirm prepared this turn joins the cards of the proposed records (sp5 6.3)
    carry = confirm_carry(ctx, turn)
    if not changed:
        if skipped:  # a timed-out git status is no evidence of a turn without changes
            note_skipped(ctx.root, skipped)
        # the cards plumb conflicts, capture or the clarify read-back asked for, what the
        # owner's words confirmed and the settled line need no edit (R17: asked at once)
        fresh, conflicts, early = owner_cards(ctx, core, turn)
        shown: dict[str, str] = {}
        text = understand_parts(ctx, core, turn, extra=carried_cards(core, carry, turn_start),
                                fresh=fresh, shown=shown)
        write_stated(ctx, turn, {}, [], confirm=carried_view(carry, shown),
                     conflicts=conflicts, early=early)
        return HookOutput(system_message="\n".join(text)) if text else None
    # no soft-budget check before the read-back (R1): only the watchdog bounds it
    index = core.index()
    by_path = core.records_for_paths(changed)
    touched_ids = sorted({i for ids in by_path.values() for i in ids if i in index})
    changed_set = set(changed)
    edited_ids = [i for i in touched_ids if index[i].path in changed_set]
    all_statuses = core.status()
    from plumb.trace import trace_instruction, untraced_paths

    # work no requirement owns escaped the translation chain: the agent is told to read it
    # back and record a proposed SR (non-blocking, R1)
    untraced = untraced_paths(core, changed)
    told_raw = turn.get("untraced_told")
    told = {str(p) for p in told_raw} if isinstance(told_raw, list) else set()

    # trigger 2: decisions that matter, unconfirmed, touched this turn
    decisions = matters_decisions(index, all_statuses, touched_ids)
    # R11 "ONE per message": only the earliest open decision is asked; the next one waits
    # until it is answered (plumb.capture.api.next_question, sp2 5.3)
    first = decisions[:1]
    open_decisions = [d for d in first if asked.get(d) != index[d].hash]
    stated_ids = [i for i in edited_ids
                  if all_statuses[i].confirmation != "confirmed"]
    for d in decisions:
        if d not in stated_ids:
            stated_ids.append(d)
    from plumb.present.cards import session_intent

    intent_summary = session_intent(core, index, touched_ids, session_dir)
    # R1 first: the cards of the proposed records and of the decisions that matter, from the
    # record states alone, are kept before any evidence step, so a cut (budget, error,
    # watchdog) still shows them; kept before the stated set says "shown", never after
    early_snapshot = build_snapshot(core, statuses=all_statuses, auto_approve="off",
                                    tests_summary=("unknown", (), ()),
                                    intent_summary=intent_summary)
    stamp = int(turn_start)
    decision_cards = [card_text.decision_card(index, index[d], touched=touched_ids, turn=stamp)
                      for d in decisions]
    # SR-030: a confirmed requirement whose acceptance test changed since the owner confirmed
    # it waits for the owner on its own card (never only in plumb status); it stays out of the
    # stated set, so a bare "ok" never confirms the new test (the card recommends putting the
    # test back)
    test_changed = [i for i in touched_ids if index[i].kind == "requirement"
                    and getattr(all_statuses.get(i), "changed_tests", ())]
    test_cards = [card_text.test_changed_card(index[i], all_statuses[i].changed_tests,
                                              turn=stamp) for i in test_changed]
    proposed = proposed_cards(core, index, all_statuses, stated_ids,
                              [*decisions, *test_changed], carry, stamp)
    kept: dict[str, str] = {}
    ctx.keep(drawn_now(core, [*decision_cards, *test_cards, *proposed], kept))
    write_stated(ctx, turn, index, stated_ids, kept, confirm=carried_view(carry, kept))
    # then the status line: a later cut (budget, watchdog) must not leave it on an older turn
    write_snapshot(ctx.root, early_snapshot, present=getattr(core.config, "present", None))
    note_path = session_dir / "untraced.json"
    queued = [p for p in untraced if p not in told]
    if queued:  # delivered by the next prompt hook, so a cut after this still tells the agent
        write_json_atomic(note_path, {"paths": queued,
                                      "prompt_digest": turn.get("prompt_digest")})

    verify = verify_api(core, verify)
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
    regressions = sorted(regressing)
    open_regressions = [n for n in regressions
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
    questions = ([f"regression {n}" for n in regressions]
                 + [f"regression hidden by a test change {m['node']}" for m in masked]
                 + decisions)
    snapshot = build_snapshot(
        core, evidence=evidence, full_pending=pending, statuses=all_statuses,
        deferred=len(selection.deferred) if selection else 0, fidelity_unjudged=fidelity,
        ask=len(questions), skipped=", ".join(skipped) or None,
        intent_summary=intent_summary)
    write_snapshot(ctx.root, snapshot, present=getattr(core.config, "present", None))
    # sp6 9.2, 9.4, R17: publish this worktree's changes, keep its intent in flight in step,
    # and the overlap lines of the records this turn touched (each once per other version)
    from plumb.awareness.turn import at_stop

    aware = at_stop(core, changed, touched_ids, ctx.deadline)
    # R17: an early conflict this turn's claim raised is asked now (the agent shows the
    # card the owner then sees at the end of the turn, and asks before any further work)
    early_ask = [line for line in aware if line.must]
    aware = [line for line in aware if not line.must]
    stale_reasons, _ = stale_hold(ctx, core, index, turn, turn_start)

    if not active:
        from plumb.present.delta import Line, open_emitter

        # the agent's instructions go through the one emitter (sp5 3): each once per
        # session per state; the triggers and the tests instruction are never cut
        emitter = open_emitter(ctx, "stop", config=core.config)
        wanted: list[Line] = []
        if not_run or unselected:
            wanted.append(Line(tests_instruction(changed,
                                                 float(core.config.verify.turn_budget_s)),
                               subject="tests", must=True, per_turn=True))
        wanted.extend(early_ask)
        for d in open_decisions:
            wanted.append(Line(_dec_question(index[d]), subject=f"question:{d}",
                               state=index[d].hash, must=True))
            asked[d] = index[d].hash
        for n in open_regressions:
            wanted.append(Line(_regression_line(n, regressing[n]), subject=f"regression:{n}",
                               state=regressing[n].last_run or "?", must=True))
            asked[f"regression:{n}"] = regressing[n].last_run or "?"
        for m in open_masked:
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
            # a blocked stop shows the owner nothing: a bare "ok" relays no record
            write_stated(ctx, turn, index, stated_ids)
            write_json_atomic(turn_path, {**turn, "asked": asked,
                                          "untraced_told": sorted(told | set(queued))})
            return HookOutput(block_reason="\n".join(reasons))
    elif stale_reasons:
        # the host says this stop already followed a block: only the stale hold repeats, up to
        # hooks.stale_holds_max times (stale.hold_count), so a turn is never held forever
        write_stated(ctx, turn, index, stated_ids)
        return HookOutput(block_reason="\n".join(stale_reasons))

    # cards only (SR-012, sp7-realign-sp8 C7): what the owner's words confirmed, the settled
    # line, then every card in full; the status card is the status line's, the agent's lines
    # are the block's
    passing = [n for n, e in (evidence or {}).items() if e.state in ("fresh-pass", "flaky-pass")]
    regression, changes = regression_cards(core, index, regressing, masked, changed, stamp)
    for card, record_id in zip(test_cards, test_changed, strict=True):
        changes[card.id] = turn_change(core, index, all_statuses[record_id].changed_tests[0],
                                       changed)
    fresh, conflicts, early = owner_cards(ctx, core, turn)
    shown: dict[str, str] = {}
    text = understand_parts(ctx, core, turn,
                            extra=[*regression, *test_cards, *decision_cards, *proposed],
                            fresh=fresh, changes=changes, passing=passing, shown=shown)
    write_stated(ctx, turn, index, stated_ids, shown, confirm=carried_view(carry, shown),
                 conflicts=conflicts, early=early)
    return HookOutput(system_message="\n".join(text)) if text else None


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


def carried_view(carry: ConfirmView, shown: Mapping[str, str]) -> ConfirmView:
    """What ``plumb confirm`` prepared, with the records a card drew in full marked shown
    (sp5 6.3: only what is shown is relayable). Its triage groups are not drawn (DEC-029: one
    card per feature replaces them), so none is relayable."""
    drawn = {str(r["id"]): shown[str(r["id"])] for r in carry.records if str(r["id"]) in shown}
    return ConfirmView(records=carry.records, groups=carry.groups, shown=drawn)


def carried_cards(core: Any, carry: ConfirmView, stamp: float) -> list[Any]:
    """The proposed cards of the records ``plumb confirm`` prepared this turn (a turn that
    changed no file)."""
    if not carry.records:
        return []
    index = core.index()
    ids = [str(r["id"]) for r in carry.records if str(r["id"]) in index]
    statuses = core.status(ids) if ids else {}
    return proposed_cards(core, index, statuses, ids, (), ConfirmView(), int(stamp))


def proposed_cards(core: Any, index: Mapping[str, Any], statuses: Mapping[str, Any],
                   stated_ids: Sequence[str], decisions: Sequence[str], carry: ConfirmView,
                   stamp: int) -> list[Any]:
    """SR-012 EX-1, EX-3, EX-4: the records this turn proposed (and ``plumb confirm``
    prepared) that are neither confirmed nor settled, one card per feature (DEC-029); the
    records of ``decisions`` (a decision that matters, a requirement whose acceptance test
    changed) have their own card."""
    from plumb.understand import cards as card_text

    wanted = [*stated_ids, *(str(r["id"]) for r in carry.records)]
    ids = []
    for record_id in dict.fromkeys(wanted):
        state = statuses.get(record_id)
        if record_id not in index or record_id in decisions or state is None:
            continue
        if state.confirmation == "confirmed" or state.settled or state.superseded_by:
            continue
        ids.append(record_id)
    return card_text.proposed_cards(index, ids, turn=stamp)


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


def turn_change(core: Any, index: Mapping[str, Any], node: str,
                changed: Sequence[str]) -> dict[str, Any] | None:
    """This turn's change behind a regression, as evidence (SR-116): the working-tree diff of
    the changed paths the failing test's requirements are implemented by (and the test file
    itself), else of the turn's changed code. None when git shows no diff."""
    from plumb.understand import cardcontent
    from plumb.understand.cards import verifying

    changed_set = set(changed)
    ends = {link.target.path for record in verifying(index, node) for link in record.links
            if link.kind == "implemented_by" and link.target.path}
    paths = sorted((ends | {node.split("::", 1)[0]}) & changed_set)
    if not paths:
        paths = [p for p in changed if is_code_path(core.config, p)][:MAX_INSTRUCTION_PATHS]
    if not paths:
        return None
    try:
        result = subprocess.run(["git", "diff", "HEAD", "--", *paths], cwd=core.root,
                                capture_output=True, timeout=GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    diff = result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else ""
    if not diff.strip():
        return None
    return {"path": ", ".join(paths), "diff": diff, "note": "",
            **cardcontent._measure(diff)}


def regression_cards(core: Any, index: Mapping[str, Any], regressing: Mapping[str, Any],
                     masked: Sequence[Mapping[str, Any]], changed: Sequence[str],
                     stamp: int) -> tuple[list[Any], dict[str, Any]]:
    """SR-012 EX-2: a card per regression (and per regression a test change hid), with this
    turn's change as its evidence."""
    from plumb.understand import cards as card_text

    out: list[Any] = []
    changes: dict[str, Any] = {}
    try:
        for node in sorted(regressing):
            found = regressing[node]
            card = card_text.regression_card(
                index, node, last_run=str(found.last_run or ""),
                test_changed=bool(getattr(found, "test_changed_since_pass", False)), turn=stamp)
            out.append(card)
            changes[card.id] = turn_change(core, index, node, changed)
        for item in masked:
            card = card_text.regression_card(index, str(item["node"]), hidden=True, turn=stamp)
            out.append(card)
            changes[card.id] = turn_change(core, index, str(item["node"]), changed)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return out, changes
    return out, changes




def stale_hold(ctx: HookContext, core: Any, index: Mapping[str, Any],
               turn: Mapping[str, Any], turn_start: float) -> tuple[list[str], list[str]]:
    """SR-111 EX-3: ``(block reasons, summary lines)`` for the links this turn made stale.

    A stale link the turn caused (against the baseline the prompt hook wrote) that no card
    holds keeps the turn open, naming it, up to ``hooks.stale_holds_max`` consecutive holds;
    then the turn is let go with a stale card per link. The links stale before the turn are
    listed once per session and never block. Without a baseline of this turn nothing is
    held. Never fails the stop."""
    try:
        from plumb import stale

        turn_id = turn.get("turn_id")
        state = stale.turn_state(core, ctx.session_id, str(turn_id) if turn_id else None)
        if not state.valid:
            return [], []
        before = []
        if state.before and stale.once_per_session(
                ctx.root, ctx.session_id, "before:" + ",".join(r.link for r in state.before)):
            before = [stale.before_line(state.before)]
        open_rows = stale.unresolved(core, ctx.session_id, state)
        held = stale.hold_count(ctx.root, ctx.session_id, str(turn_id))
        if not open_rows:
            if held:
                stale.set_hold_count(ctx.root, ctx.session_id, str(turn_id), 0)
            return [], before
        limit = int(core.config.hooks.stale_holds_max)
        if ctx.extra.get("host"):
            limit = min(limit, 1)  # the host-neutral path blocks at most once per turn
        if held < limit:
            stale.set_hold_count(ctx.root, ctx.session_id, str(turn_id), held + 1)
            missing = stale.incomplete_cards(ctx.root, ctx.session_id)
            return [*stale.hold_lines(open_rows, held + 1, limit, missing), *before], []
        from plumb.present.owner_text import STALE_HOLD_ENDED

        notes = []
        for row in open_rows:
            title = index[row.record].title if row.record in index else row.record
            other = index[row.what].title if row.what in index else ""
            stale.add_card(ctx.root, ctx.session_id, turn=int(turn_start),
                           **stale.default_card(row, title, other))
            notes.append(STALE_HOLD_ENDED.format(n=held, title=title))
        return [], [*before, *notes]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return [], []


def understand_parts(ctx: HookContext, core: Any, turn: Mapping[str, Any], *,
                     extra: Sequence[Any] = (), fresh: Sequence[Any] = (),
                     changes: Mapping[str, Any] | None = None, passing: Sequence[str] = (),
                     shown: dict[str, str] | None = None) -> list[str]:
    """SR-105, SR-012: the owner's whole text at the end of a turn: what they confirmed by
    their words, the settled line, then the cards (``understand.summary.stop_parts``, which
    draws every card in full and keeps ``extra`` open across turns while it holds). Never
    fails the stop."""
    try:
        from plumb.understand.summary import stop_parts

        parts = stop_parts(ctx, core, turn, extra=extra, fresh=fresh, changes=changes,
                           passing=passing, shown=shown)
        bag = getattr(ctx, "extra", None)
        if isinstance(bag, dict):
            bag["stop_parts"] = parts       # what present.json carries while the panel is on
        return [*parts.confirmations, *parts.settled, *parts.cards]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return []


def owner_cards(ctx: HookContext, core: Any, turn: Mapping[str, Any]
                ) -> tuple[list[Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """``(cards, conflict stated entries, early stated entries)``: a card per intent conflict
    a merge left (sp6 8.3), drawn at every turn end while it is open, and per early conflict
    ``capture`` or ``plumb clarify`` asked for this turn (R17); their stated entries let the
    owner's next words choose a side (8.4). Never fails the stop."""
    from plumb.understand import cards as card_text

    index = core.index()
    stamp = int(float(turn.get("turn_start") or 0))
    out: list[Any] = []
    conflicts: list[dict[str, Any]] = []
    early: list[dict[str, Any]] = []
    try:
        from plumb.mergedriver.conflicts import open_conflicts, stated_entries

        found = open_conflicts(core)
        out += [card_text.conflict_card(index, c, turn=stamp) for c in found]
        conflicts = stated_entries(core, [c.ic for c in found])
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        pass
    start = _iso(float(turn.get("turn_start") or 0)) if turn.get("turn_start") else ""
    try:
        from plumb.awareness.early import stated_entry, turn_conflicts

        for conflict in turn_conflicts(ctx.session_dir, start):
            out.append(card_text.early_conflict_card(index, conflict, turn=stamp))
            early.append(stated_entry(conflict))
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        pass
    return out, conflicts, early


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
