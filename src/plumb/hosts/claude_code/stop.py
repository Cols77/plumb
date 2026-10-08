"""Stop: covering tests within the budget, the three triggers, then the summary (spec 6.4).

1. This turn's changed paths: the session's ``touched.txt`` plus every path of one
   ``git status`` call whose mtime is at or after the turn start.
2. Their records (``CoreAPI.records_for_paths``), the link states of those records only, the
   covering selection (``VerifyAPI.select``) and its evidence.
3. The read-back comes first (R1): the summary from the record states alone, with the
   proposed records, is kept (``HookContext.keep``) before any evidence step, so a budget
   cut, an error or the watchdog still prints it. Then the covering tests and fidelity.
   Write ``status.json`` and the stated set (``stated.json``). Each stated record carries
   ``shown``: true only when the summary displayed its intent card (sp5 4.2), which shows
   the whole read-back (statement, every example, will/won't, labelled assumptions,
   alternatives). A bare affirmation relays only
   shown records; a record cut by ``hooks.summary_proposed_cap`` (counted in records) or too
   long to show, or any record of a blocked stop, must be named in the owner's words.
4. At most one block per turn, never when the host says ``stop_hook_active``: covering tests
   without fresh evidence (the agent runs ``plumb tests run --paths <this turn's paths>`` in
   its turn; the hook never runs pytest), an unconfirmed decision that matters (trigger 2,
   once per hash) and a regression (trigger 3, R3: a node that passed with recorded
   evidence and now fails; once per failing run). A new test that starts red is "not yet
   passing" and never asks. The block's lines go through the one emitter
   (``plumb.present.delta``): each once per session per state, within
   ``hooks.stop_tokens``; the covering-tests instruction and the skipped-check notice are
   about this turn (``per_turn``), so every turn whose covering tests lack fresh evidence
   blocks once, whatever the prompt's words.
5. Otherwise the owner-facing ``systemMessage``: the status card, the summary lines for
   ``present.card`` (full | compact | off) and the intent cards of the records that matter
   (sp5 4); proposed records are shown, never asked, and the ones not shown are named with
   the ``plumb show`` command that prints them. The triage offer (R8 A) pins its group in
   the stated set. The records and the triage group ``plumb confirm`` prepared this turn
   are rendered here, as full intent cards and the group's offer line, and only what is
   rendered is marked shown (``confirm_view``, sp5 6.3).

The deadline is checked before a step starts, never after it ends (spec 10): a step that
would start past the soft budget is skipped and named in a ``check skipped (budget)`` notice,
and results already computed are always used (the stated set, the snapshot, the block and the
summary). The record states and the read-back are never skipped by the soft budget: only the
watchdog's hard limit bounds them, and it prints whatever was kept.
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
SUMMARY_LINES = 5
GIT_TIMEOUT_S = 1.0  # most of the soft budget: under load git status alone can take 0.6 s
GIT_SKIPPED = "change detection (git status)"
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


def changed_paths(root: Path, touched_file: Path, turn_start: float,
                  timeout: float = GIT_TIMEOUT_S,
                  skipped: list[str] | None = None) -> list[str]:
    """This turn's paths. A ``git status`` that timed out is named in ``skipped``."""
    seen: dict[str, None] = {}
    for rel in _touched(touched_file):
        if not _ignored(rel):
            seen.setdefault(rel, None)
    if turn_start > 0:
        status = _git_status(root, timeout)
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


def changed_acceptance(index: Mapping[str, Any], statuses: Mapping[str, Any],
                       touched_ids: Iterable[str]) -> list[str]:
    """``SR-001 tests/test_mod.py (EX-1) changed since you confirmed it``: touched
    requirements whose acceptance test content no longer matches the owner's approval. Shown
    in the summary, never asked (R1); the merge boundary waits for the owner on it."""
    out = []
    for record_id in touched_ids:
        status = statuses.get(record_id)
        ends = getattr(status, "changed_tests", ()) if status is not None else ()
        if not ends:
            continue
        record = index[record_id]
        for end in ends:
            examples = [link.example for link in record.links if link.kind == "verified_by"
                        and (link.target.test or link.target.path) == end and link.example]
            what = f" ({', '.join(examples)})" if examples else ""
            out.append(f"acceptance test changed since you confirmed it: {record_id} "
                       f"{end}{what}, awaits your confirmation (plumb show {record_id})")
    return out


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
    the owner-facing lines (the group's offer and a full intent card per record), the
    records rendered (``id -> hash``) and the groups whose offer was rendered."""

    records: list[dict[str, Any]] = field(default_factory=list)
    groups: list[dict[str, Any]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    shown: dict[str, str] = field(default_factory=dict)
    shown_groups: list[dict[str, Any]] = field(default_factory=list)


CONFIRM_HEADER = ("plumb confirm: say \"ok\" to confirm what is shown below, or name the "
                  "records; nothing is approved until you do")


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
    return ConfirmView(records=records, groups=groups)


def confirm_view(core: Any, carry: ConfirmView, skip: Iterable[str] = ()) -> ConfirmView:
    """The one place ``plumb confirm``'s records reach the owner (sp5 6.3, R2): each
    prepared record as a full intent card, and each prepared group's offer line when every
    record it pins is unchanged. Only what is rendered here is marked shown; ``skip`` are
    records the summary already carded in full (shown by it)."""
    if not carry.records and not carry.groups:
        return carry
    from plumb.present.cards import card_data
    from plumb.present.render import intent_card

    index = core.index()
    ascii_only = bool(getattr(getattr(core.config, "present", None), "ascii", False))
    skip = set(skip)
    lines: list[str] = []
    shown_groups: list[dict[str, Any]] = []
    for group in carry.groups:
        pinned = [r for r in group.get("records") or [] if isinstance(r, dict)]
        current = pinned and all(r.get("id") in index and index[r["id"]].hash == r.get("hash")
                                 for r in pinned)
        if current and group.get("offer"):
            lines.append(str(group["offer"]))
            shown_groups.append({k: v for k, v in group.items() if k not in ("offer", "via")})
        else:
            lines.append(f"plumb: the {group.get('group')} group changed since it was "
                         "prepared; /plumb confirm shows it again")
    wanted = [str(r["id"]) for r in carry.records if r["id"] in index and r["id"] not in skip]
    shown: dict[str, str] = {}
    for data in card_data(core, list(dict.fromkeys(wanted))):
        if _too_long(data):
            lines.append(f"plumb: {data.id} is too long to show here (plumb show {data.id}); "
                         "a confirmation must name it")
            continue
        lines.extend(intent_card(data, mode="full", ascii=ascii_only))
        shown[data.id] = index[data.id].hash
    if lines:
        lines.insert(0, CONFIRM_HEADER)
    return ConfirmView(records=carry.records, groups=carry.groups, lines=lines, shown=shown,
                       shown_groups=shown_groups)


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
    skipped: list[str] = []
    changed = changed_paths(ctx.root, session_dir / "touched.txt", turn_start,
                            min(GIT_TIMEOUT_S, max(ctx.deadline.remaining_s(), 0.05)),
                            skipped)
    from plumb.api import open_core
    from plumb.hosts.claude_code.snapshot import build_snapshot, write_snapshot

    core = open_core(ctx.root)
    # what plumb confirm prepared this turn reaches the owner here, as full cards (sp5 6.3)
    carry = confirm_carry(ctx, turn)
    if not changed:
        view = confirm_view(core, carry)
        # the cards plumb conflicts, capture or the clarify read-back asked for this turn
        # reach the owner even when the turn changed no file (R17: asked at once)
        conflict_lines, conflicts = conflict_cards(ctx, core, turn)
        early_lines, early = early_cards(ctx, turn)
        write_stated(ctx, turn, {}, [], confirm=view, conflicts=conflicts, early=early)
        # a timed-out git status is no evidence of a turn without changes
        text = [*view.lines, *conflict_lines, *early_lines,
                *([skip_notice(skipped)] if skipped else [])]
        return HookOutput(system_message="\n".join(text)) if text else None
    # no soft-budget check before the read-back (R1): only the watchdog bounds it
    index = core.index()
    by_path = core.records_for_paths(changed)
    touched_ids = sorted({i for ids in by_path.values() for i in ids if i in index})
    changed_set = set(changed)
    edited_ids = [i for i in touched_ids if index[i].path in changed_set]
    all_statuses = core.status()
    from plumb.trace import trace_instruction, untraced_paths

    # work no requirement owns escaped the translation chain: the owner sees it named, the
    # agent is told to read it back and record a proposed SR (non-blocking, R1)
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
    # the cards' triggers known from the records alone (sp5 4.2): this turn's intent-change
    # flags (trigger 1, from the prompt hook) and escalated sets awaiting approval
    flagged = concluded_flags(index, turn, edited_ids)
    escalated, waiting = escalated_sets(core, touched_ids)
    from plumb.present.cards import session_intent

    intent_summary = session_intent(core, index, touched_ids, session_dir)
    # R1 first: the read-back is kept before any evidence step, so a cut (budget, error,
    # watchdog) still shows it; kept before the stated set says "shown", never after
    early_snapshot = build_snapshot(core, statuses=all_statuses, auto_approve="off",
                                    tests_summary=("unknown", (), ()),
                                    intent_summary=intent_summary)
    early, early_shown = summary(
        core, index, all_statuses, changed, touched_ids, stated_ids, None, None, None,
        decisions, (), 0.0, True, tests_checked=False, untraced=untraced,
        changed_tests=changed_acceptance(index, all_statuses, touched_ids),
        snapshot=early_snapshot, decisions=decisions, flagged=flagged, escalated=escalated,
        extra_lines=waiting)
    early_view = confirm_view(core, carry, early_shown)
    ctx.keep([*early.splitlines(), *early_view.lines])
    write_stated(ctx, turn, index, stated_ids, early_shown, confirm=early_view)
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
    # card the owner then sees in the reply, and asks before any further work)
    early_ask = [line for line in aware if line.must]
    aware = [line for line in aware if not line.must]

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

    if ctx.deadline.expired():
        skipped.append("confirmations")
        turn_start = 0.0  # _confirmations reads no log without a turn start
    # a group plumb confirm prepared this turn is the offer; this turn's own is not added
    offer, group = ([], None) if ctx.deadline.expired() or carry.groups else triage_offer(
        core, [i for i in stated_ids if all_statuses[i].confirmation != "confirmed"])
    if aware:
        from plumb.present.delta import emit

        offer = [*offer, *emit(ctx, aware, "stop", config=core.config)]
    text, shown = summary(
        core, index, all_statuses, changed, touched_ids, stated_ids, selection, evidence,
        pending, questions, fidelity, turn_start, verify is not None, skipped,
        tests_checked="covering tests" not in skipped or recorded is not None,
        untraced=untraced,
        changed_tests=changed_acceptance(index, all_statuses, touched_ids),
        snapshot=snapshot, decisions=decisions,
        regressions=[*regressions, *(m["node"] for m in masked)], flagged=flagged,
        escalated=escalated, extra_lines=[*waiting, *offer])
    view = confirm_view(core, carry, shown)
    message = "\n".join([text, *view.lines]) if view.lines else text
    conflict_lines, conflicts = conflict_cards(ctx, core, turn)
    if conflict_lines:
        message = "\n".join([message, *conflict_lines])
    early_lines, early = early_cards(ctx, turn)
    if early_lines:
        message = "\n".join([message, *early_lines])
    write_stated(ctx, turn, index, stated_ids, shown, group=group, offer=offer,
                 message=message, confirm=view, conflicts=conflicts, early=early)
    return HookOutput(system_message=message)


def early_cards(ctx: HookContext,
                turn: Mapping[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """R17: the early intent-conflict cards ``capture`` or ``plumb clarify`` asked for this
    turn, shown to the owner with their stated entries, so the owner's answer in the card's
    words ("keep feat-x's") is relayed against a card the owner saw. Never fails the stop."""
    start = _iso(float(turn.get("turn_start") or 0)) if turn.get("turn_start") else ""
    try:
        from plumb.awareness.early import turn_cards

        return turn_cards(ctx.session_dir, start)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return [], []


def conflict_cards(ctx: HookContext, core: Any,
                   turn: Mapping[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """sp6 8.3: the intent conflicts a merge left, as full cards in the turn they appear
    (once per conflict version per session) and whenever ``plumb conflicts`` asked; their
    stated entries let the owner's next words choose a side (8.4). Never fails the stop."""
    try:
        from plumb.mergedriver.conflicts import turn_cards
    except ImportError:
        return [], []
    start = _iso(float(turn.get("turn_start") or 0)) if turn.get("turn_start") else ""
    try:
        return turn_cards(core, ctx.session_dir, ctx.session_id, start)
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return [], []


# links by which a record written or edited this turn says it changes another one
_CHANGE_LINKS = ("supersedes", "corrects", "relates_to", "derives_from", "decides")


def concluded_flags(index: Mapping[str, Any], turn: Mapping[str, Any],
                    edited_ids: Sequence[str]) -> list[str]:
    """The prompt hook's intent-change flags (trigger 1) the owner sees as a card: only
    those the turn shows a change for. The prompt hook's flag is an instruction to the agent,
    which is the cascade's LLM tier (concept 6.2); a heuristic flag alone never reaches the
    owner (decision 5: "few, meaningful interruptions").

    A flag counts when the agent edited the flagged record this turn, or wrote or edited a
    record that links to it (supersedes, corrects, relates to, derives from or decides it),
    or when a judgment backend other than the heuristic rated it ``accept`` (confident)."""
    raw = [str(i) for i in turn.get("flagged") or [] if str(i) in index]
    if not raw:
        return []
    details = turn.get("flags") if isinstance(turn.get("flags"), Mapping) else {}
    edited = set(edited_ids)
    linked = {link.target.record for i in edited if i in index for link in index[i].links
              if link.kind in _CHANGE_LINKS and link.target.record}
    out = []
    for record_id in raw:
        info = details.get(record_id) if isinstance(details.get(record_id), Mapping) else {}
        confident = info.get("tier") == "accept" and info.get("backend") not in (
            None, "", "heuristic")
        if record_id in edited or record_id in linked or confident:
            out.append(record_id)
    return out


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


def escalated_sets(core: Any, touched_ids: Sequence[str]) -> tuple[list[str], list[str]]:
    """``(anchors, lines)``: escalated sets (CAPTURE, sp2 6.2) a touched record belongs to
    that await the owner's set approval; a question card each (trigger 2)."""
    try:
        from plumb.capture import spec
    except ImportError:
        return [], []
    try:
        members = spec.set_of(core)
        anchors = sorted({members[i] for i in touched_ids if i in members})
        lines = [line for line in (spec.waiting_line(core, a) for a in anchors) if line]
        waiting = [a for a in anchors if spec.set_state(core, a) != "approved"]
    except Exception:  # noqa: BLE001 - an advisory lane never fails the stop
        return [], []
    return waiting, lines


def triage_offer(core: Any, ids: Sequence[str]) -> tuple[list[str], Any]:
    """R8 A: the one-line offer for this turn's proposed records rated faithful to the
    owner's words (CAPTURE's triage) and the group it pins in the stated set (DEC-017)."""
    if not ids:
        return [], None
    try:
        from plumb.capture import api
    except ImportError:
        return [], None
    try:
        view = api.triage(core, ids)
        group = api.stated_group(view) if view.offer else None
    except Exception:  # noqa: BLE001
        return [], None
    return ([str(view.offer)] if view.offer else []), group


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
            verify_available: bool, skipped: Sequence[str] = (), *,
            tests_checked: bool = True,
            untraced: Sequence[str] = (),
            changed_tests: Sequence[str] = (),
            snapshot: Any = None, decisions: Sequence[str] = (),
            regressions: Sequence[str] = (), flagged: Sequence[str] = (),
            escalated: Sequence[str] = (), extra_lines: Sequence[str] = ()
            ) -> tuple[str, list[str]]:
    """The owner-facing summary and the stated ids it showed in full (sp5 4).

    The status card comes first; then the sp1 summary lines (``present.card: full``), at
    most two of them (``compact``, the default) or none (``off``); then the intent cards of
    ``plumb.present.cards``: trigger cards always, the proposed records of the turn (and,
    in ``full``, every record it touched) up to ``hooks.summary_proposed_cap``. A carded
    record is shown in full; the rest are named with ``plumb show``.

    ``tests_checked`` False (the covering tests were not evaluated, or not yet): the
    questions line says the regression check did not run, never "none"."""
    from plumb.present.cards import card_data, card_mode, plan_cards
    from plumb.present.render import intent_card, status_card, to_ascii

    present = getattr(core.config, "present", None)
    mode = card_mode(core.config)
    ascii_only = bool(getattr(present, "ascii", False))
    lines = sp1_lines(core, index, statuses, changed, touched_ids, selection, evidence,
                      pending, questions, fidelity, turn_start, verify_available, skipped,
                      tests_checked=tests_checked, untraced=untraced,
                      changed_tests=changed_tests)
    if mode == "compact" and len(lines) > 2:
        rest = [line.removeprefix("plumb: ") for line in lines[1:]]
        lines = [lines[0], "plumb: " + " | ".join(rest)]
    elif mode == "off":
        lines = []
    head = [status_card(snapshot, ascii=ascii_only)] if snapshot is not None and \
        mode != "off" else []
    plan = plan_cards(mode=mode, index=index, statuses=statuses, stated=stated_ids,
                      decisions=decisions, regressions=regressions, flagged=flagged,
                      escalated=escalated, touched=touched_ids,
                      cap=int(core.config.hooks.summary_proposed_cap))
    why = dict(plan.cards)
    cards: list[str] = []
    too_long: list[str] = []
    for data in card_data(core, plan.shown, evidence=evidence if evidence else None):
        if why.get(data.id) is None and _too_long(data):
            too_long.append(data.id)  # not shown at all: a confirmation must name it
            continue
        cards.extend(intent_card(data, mode=mode, why=why.get(data.id), ascii=ascii_only))
    plan.cards = [(i, w) for i, w in plan.cards if i not in too_long]
    cards.extend(to_ascii(line) if ascii_only else line for line in plan.loose)
    cut = [i for i in stated_ids if i not in plan.shown]
    if cut and mode != "off":
        cards.append(f"plumb: +{len(cut)} more not shown: {', '.join(cut)} "
                     f"(plumb show {' '.join(cut)}); a confirmation must name them")
    out = [*head, *lines, *cards, *(line for line in extra_lines if mode != "off"
                                     or "escalated" in line)]
    return "\n".join(out), [i for i in plan.shown if i in stated_ids]


def _too_long(data: Any) -> bool:
    """A card part too long to show whole (``MAX_PROPOSED_LINE``): the record is not shown."""
    parts = [data.statement, data.quote, *data.will, *data.wont, *data.assumed,
             *data.alternatives, *(text for _, _, text in data.examples)]
    return any(len(part) > MAX_PROPOSED_LINE for part in parts)


def sp1_lines(core: Any, index: Mapping[str, Any], statuses: Mapping[str, Any],
              changed: Sequence[str], touched_ids: Sequence[str], selection: Any,
              evidence: Mapping[str, Any] | None, pending: Any, questions: Sequence[str],
              fidelity: Sequence[str], turn_start: float, verify_available: bool,
              skipped: Sequence[str] = (), *, tests_checked: bool = True,
              untraced: Sequence[str] = (), changed_tests: Sequence[str] = ()) -> list[str]:
    """The sp1 summary lines (at most five): touched records, covering tests, full
    verification, confirmations and notes, questions."""
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
    if untraced:
        names = ", ".join(untraced[:3]) + (f" +{len(untraced) - 3} more"
                                           if len(untraced) > 3 else "")
        touched += f" | untraced: {names} (read-back and a proposed SR requested)"
    if doc_only and not records_edited:
        return [touched + " | docs only, no tests selected"]
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
    extra = list(changed_tests)
    if confirmed:
        extra.append("; ".join(confirmed))
    if fidelity:
        extra.append("fidelity unjudged: " + ", ".join(fidelity))
    if skipped:
        extra.append(skip_notice(skipped).removeprefix("plumb: "))
    if extra:
        lines.append(_clip("plumb: " + " | ".join(extra), 200))
    asks = list(questions)
    if not tests_checked and verify_available:
        asks.append("regressions not checked (budget)")
    lines.append("plumb: questions: " + ("; ".join(asks) if asks else "none"))
    return lines[:SUMMARY_LINES]


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, unjudged: Any = LAZY) -> int:
    return run_hook("stop", lambda ctx: handle(ctx, verify=verify, unjudged=unjudged),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("stop"),
                    json_output=True, watchdog=watchdog, start=start)
