"""UserPromptSubmit: a compact delta of the relevant records and the intent-change flag
(spec 6.2, ruling R9 context economy).

1. Log the prompt (digest, session, time, text) to ``.plumb/session/prompts.jsonl`` and
   start the turn (``turn.json``). This comes first: the reader job and typed commands rely on it.
2. Queue the read of the owner's answer and say so (``understand_lines``). Nothing here
   reads the owner's words for approval, and the agent is told to confirm nothing: the
   worker applies the model's reading (INT-028, INT-029).
3. Print the relevant records (named IDs first) as one line each (ID, state, title), ONLY
   when the record is newly relevant this session or changed (its content hash or its
   confirmation state) since it was last injected (``.plumb/session/<id>/seen.json``), within
   ``hooks.prompt_lines`` lines and the ``hooks.prompt_tokens`` budget. Examples and covering
   tests are pulled on demand (``plumb show <ID>``); nothing is injected when nothing new is
   relevant.
4. Flag a possible intent change on a confirmed record (``JudgmentBackend``), and, with the
   confirmed records first injected in this prompt, ask the agent to compare the request
   with their examples.
5. Print queued escalations and the escalation hint (SHOULD items), and the untraced change
   the stop hook queued (a changed source path no requirement owns: read it back and record
   a proposed SR).

Every line goes through the one emitter, ``plumb.present.delta`` (sp5 3): the compare line,
escalations and the untraced instruction reach the agent once per session per state. The
intent-change flags are about this turn (``per_turn``): every request that may change a
confirmed record is flagged, not only the first one of the session (decision 5, trigger 1).
Every
line is an intent-translation line computed from the records alone and kept through a
budget cut (spec 10).

Output is plain text, added to the agent's context. Questions to the owner are left to the
agent, and only on the three triggers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from plumb.approvals import prompt_origin
from plumb.hosts.claude_code.hookio import (
    HookContext,
    HookOutput,
    hook_budget,
    read_json,
    run_hook,
    write_json_atomic,
)
from plumb.hosts.claude_code.providers import LAZY, judgment_backend

STRONG_MATCH = 1.0
CHARS_PER_TOKEN = 4  # the estimate behind ``hooks.prompt_tokens``


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _clip(text: str, width: int = 100) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _append_jsonl(path: Path, item: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


# SR-112: text the harness injects into a user-role turn is not the owner's. Its envelope is
# structural and exact: these tags (an unclosed one runs to the end) and this marker line.
_ENVELOPE = re.compile(
    r"<(task-notification|system-reminder)>.*?(?:</\1>|\Z)"
    r"|^[ \t]*\[SYSTEM NOTIFICATION - NOT USER INPUT\].*\Z",
    re.DOTALL | re.MULTILINE)


def owner_text(text: str) -> str:
    """The owner's own words: ``text`` without harness-injected notification blocks."""
    return _ENVELOPE.sub("", text).strip() if _ENVELOPE.search(text) else text


def log_prompt(ctx: HookContext, text: str, origin: str = "") -> str:
    """Append the prompt to the session's prompt log and start the turn. Returns the digest."""
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    marked, from_name = prompt_origin(text)   # SR-168: as the host marked it
    origin = origin or marked
    _append_jsonl(ctx.session_dir / "prompts.jsonl",
                  {"digest": digest, "session": ctx.session_id, "at": _utc_now(),
                   # R13 Q4: "hook" only from a host's prompt hook; `plumb turn start`
                   # (the agent records the message itself) passes via "turn"
                   "text": text, "via": str(ctx.extra.get("via") or "hook"),
                   # which host's hook logged it: a hook-logged prompt from a host proves
                   # that host's prompt hook runs (approvals.host_logs_prompts)
                   "host": str(ctx.extra.get("host") or "claude-code"), "origin": origin,
                   **({"from_name": from_name} if from_name else {})})
    if origin != "owner":   # a peer's message starts no turn
        return digest
    turn_path = ctx.session_dir / ctx.session_id / "turn.json"
    try:  # a new turn: the touched list holds this turn's edits only
        (turn_path.parent / "touched.txt").unlink()
    except OSError:
        pass
    previous = read_json(turn_path)
    asked = previous.get("asked") if isinstance(previous, dict) else None
    # turn_id: what makes a per_turn line new (plumb.present.delta), even when two turns
    # start within one clock tick
    write_json_atomic(turn_path, {"turn_start": time.time(), "turn_id": os.urandom(8).hex(),
                                  "prompt_digest": digest,
                                  "asked": asked if isinstance(asked, dict) else {}})
    return digest


RECORDS_HEADER = ("plumb: relevant records, new or changed this session (plumb show <ID> for "
                  "examples and tests):")


def seen_key(record: Any, status: Any) -> str:
    """What makes a record worth injecting again: its content hash and its state."""
    state = status.confirmation if status is not None else "?"
    return f"{record.hash}|{state}"


def record_line(record_id: str, index: Mapping[str, Any], statuses: Mapping[str, Any]) -> Any:
    """The one delta line of a relevant record (ID, state, title), keyed by its hash and
    confirmation state (sp5 3)."""
    from plumb.present.delta import Line

    state = statuses[record_id].confirmation if record_id in statuses else "?"
    return Line(_clip(f"{record_id} [{state}] {index[record_id].title}"),
                subject=f"record:{record_id}",
                state=seen_key(index[record_id], statuses.get(record_id)),
                record=record_id, group="records")


def _relevant_ids(core: Any, text: str) -> tuple[list[str], list[str]]:
    """``(relevant ids, strongly matched ids)``: named records count as strong."""
    from plumb.query import _ID_IN_TEXT

    named = set(_ID_IN_TEXT.findall(text))
    ranked = list(core.relevant(text, limit=5))
    ids = [record_id for record_id, _ in ranked]
    strong = [record_id for record_id, score in ranked
              if record_id in named or score >= STRONG_MATCH]
    return ids, strong


def untraced_queued(ctx: HookContext, core: Any) -> list[str]:
    """The stop hook's queued untraced paths (spec 6.4), read once: paths a requirement has
    linked since are dropped, and the note is removed whatever remains. The emitter then
    tells the agent about each path once per session (sp5 3)."""
    from plumb.trace import untraced_paths

    note = ctx.session_dir / ctx.session_id / "untraced.json"
    data = read_json(note)
    if data is None:
        return []
    try:
        note.unlink()
    except OSError:
        pass
    paths = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(paths, list):
        return []
    return list(untraced_paths(core, [str(p) for p in paths]))


def untraced_line(emitter: Any, paths: Sequence[str], core: Any = None) -> Any:
    """One instruction for the untraced paths the agent has not been told about yet."""
    from plumb.present.delta import Line
    from plumb.trace import trace_instruction

    new = [p for p in paths if emitter.is_new(f"untraced:{p}")]
    if not new:
        return None
    # oneshot: the note was consumed when read, so the budget must never cut this line
    return Line(trace_instruction(new, core=core), subject="untraced:" + "|".join(sorted(new)),
                marks=tuple(f"untraced:{p}" for p in new), oneshot=True)


def escalation_lines(ctx: HookContext) -> list[str]:
    """Escalations queued by the cascade since the last print (printed once each). The
    offset moves past them on read: their lines are ``oneshot`` (never cut by the budget)."""
    queue = ctx.session_dir / "escalations.jsonl"
    try:
        size = queue.stat().st_size
    except OSError:
        return []
    marker = ctx.session_dir / "escalations.offset"
    try:
        offset = int(marker.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        offset = 0
    if offset > size:
        offset = 0
    if offset == size:
        return []
    lines = []
    with queue.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read()
    for raw in chunk.decode("utf-8", errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("instruction"):
            lines.append(_clip(f"plumb: escalation {item.get('subject', '')}: "
                               f"{item['instruction']}", 200))
    marker.write_text(str(size), encoding="utf-8")
    return lines


def escalation_hint(core: Any, index: Mapping[str, Any], strong: Sequence[str],
                    flagged: Sequence[str]) -> str | None:
    config = core.config.escalation
    requirements = [i for i in strong if index[i].kind == "requirement"]
    features = sorted({str(index[i].fields.get("feature")) for i in requirements
                       if index[i].fields.get("feature")})
    reasons = []
    if len(features) > config.max_features:
        reasons.append(f"{len(features)} features: {', '.join(features)}")
    if len(requirements) > config.max_requirements:
        reasons.append(f"{len(requirements)} requirements")
    if flagged:
        reasons.append("may change confirmed " + ", ".join(flagged))
    if not reasons:
        return None
    return (f"plumb: consider escalating to an up-front spec ({'; '.join(reasons)}); "
            "the owner decides.")


def intent_lines(ctx: HookContext, core: Any, index: Mapping[str, Any],
                 statuses: Mapping[str, Any], ids: Sequence[str], text: str, digest: str,
                 backend: Any, injected: Sequence[str] | None = None,
                 ) -> tuple[list[Any], dict[str, dict[str, Any]]]:
    """``(lines, flags)``: the trigger-1 flags on every relevant confirmed record (once
    per turn: each request that may change it is flagged, decision 5), each with the
    judgment behind it (``backend``, ``tier``, ``confidence``), and the compare line for the
    confirmed records injected in this prompt (``injected``; all of them when None).

    A flag is an instruction to the agent, the cascade's LLM tier (concept 6.2): it is never
    shown to the owner by itself (the stop hook's ``concluded_flags``)."""
    from plumb.present.delta import Line

    confirmed = [index[i] for i in ids if statuses[i].confirmation == "confirmed"]
    out: list[Any] = []
    flagged: dict[str, dict[str, Any]] = {}
    if not confirmed:
        return out, flagged
    judgments: list[Any] | None = None
    try:
        backend = judgment_backend(core, backend)
        if backend is not None:
            judgments = list(backend.intent_change(text, confirmed))
    except Exception as exc:  # noqa: BLE001 - a hook never crashes on its judge
        from plumb.judgment import JudgmentUnavailable

        judgments = None
        if isinstance(exc, JudgmentUnavailable):
            # INT-029: the cause in one line, once per session (the Line is deduplicated by
            # its subject and state); no rule-based judge answers in its place
            out.append(Line(f"plumb: judging unavailable: {exc}", subject="judging-unavailable",
                            state=str(exc)))
        else:
            out.append(Line("plumb: intent check unavailable"))
    if judgments is None:
        if backend is None and not out:
            out.append(Line("plumb: intent check unavailable"))
    else:
        for judgment in judgments:
            if judgment.verdict != "change":
                continue
            flagged[judgment.subject] = {"backend": judgment.backend, "tier": judgment.tier,
                                         "confidence": judgment.confidence}
            subject = index.get(judgment.subject)
            out.append(Line(f"plumb: this may change {judgment.subject} (confirmed). If it "
                            "does, read back the change and ask before editing; if not, "
                            "proceed.", subject=f"flag:{judgment.subject}",
                            state=getattr(subject, "hash", "") or "-", must=True,
                            # trigger 1 is about THIS request (decision 5): each prompt
                            # that may change the record gets its own instruction; only
                            # the record lines are deduplicated per session (R9)
                            per_turn=True))
            _append_jsonl(ctx.session_dir / "intent_flags.jsonl",
                          {"at": _utc_now(), "session": ctx.session_id,
                           "prompt_digest": digest, "subject": judgment.subject,
                           "confidence": judgment.confidence,
                           "backend": judgment.backend, "tier": judgment.tier})
        first = next((index[s] for s in flagged if s in index), None)
        if first is not None:
            held = intent_change_hold(ctx, digest, first)
            if held is not None:
                out.append(held)
    compare = [r.id for r in confirmed if injected is None or r.id in injected]
    if compare:
        out.append(Line("plumb: compare this request with the confirmed examples of "
                        + ", ".join(compare)
                        + "; if it contradicts or extends them, read back the change and ask "
                        "before editing.", subject="compare:" + ",".join(compare),
                        state=",".join(seen_key(index[i], statuses.get(i)) for i in compare)))
    return out, flagged


def intent_change_hold(ctx: HookContext, digest: str, record: Any) -> Any:
    """SR-196: the request changes the confirmed ``record`` and no intent loop ran for it
    (``plumb intent open`` writes ``intent/<digest12>.json`` in the session): close the edit
    gate naming the record and its examples, and say so in one line. A gate closed for
    another reason (a check in flight) is left as it is. None when nothing was closed."""
    from plumb.present.delta import Line
    from plumb.understand import files, gate

    short = digest.removeprefix("sha256:")[:12]
    if (files.session_dir(ctx.root, ctx.session_id) / "intent" / f"{short}.json").is_file():
        return None
    current = gate.state(ctx.root, ctx.session_id)
    if current.state == "closed" and not current.reason.startswith(gate.INTENT_CHANGE):
        return None
    reason = " ".join([gate.INTENT_CHANGE, record.id, *(e.id for e in record.examples)])
    gate.close(ctx.root, ctx.session_id, digest, reason)
    return Line(f"plumb: edits are held ({reason}): /plumb intent opens the loop for this "
                "request; /plumb go releases it.", subject="gate:intent-change", state=digest,
                must=True, per_turn=True)


def awareness_lines(core: Any, ids: Sequence[str]) -> list[Any]:
    """sp6 9.4: one line per relevant record another worktree or branch is changing (and
    the intent conflicts other branches raised against this one, R17), from git's and the
    other worktrees' files only: no git process on the prompt path."""
    try:
        from plumb.awareness.lines import delta_lines

        return list(delta_lines(core, ids))
    except Exception:  # noqa: BLE001 - awareness is advisory
        return []


def understand_lines(ctx: HookContext, core: Any, digest: str, text: str) -> list[str]:
    """The understanding layer's agent-facing lines for this prompt (queues its jobs); a
    failing layer never blocks the prompt."""
    try:
        from plumb.understand.hooks import on_prompt

        return list(on_prompt(ctx, core, {"digest": digest, "text": text}))
    except Exception:  # noqa: BLE001
        return []


def stale_turn_start(ctx: HookContext, core: Any) -> None:
    """SR-111: keep the link map current for the edit check and write the baseline of this
    turn (the links stale now, which the stop hook does not hold the turn for); a failure
    here never blocks the prompt."""
    try:
        from plumb.stale import ensure_linkmap, write_baseline

        ensure_linkmap(core)
        turn = read_json(ctx.session_dir / ctx.session_id / "turn.json")
        turn_id = turn.get("turn_id") if isinstance(turn, dict) else None
        if turn_id and not ctx.deadline.expired():
            write_baseline(core, ctx.session_id, str(turn_id))
    except Exception:  # noqa: BLE001 - advisory
        pass


def cards_waiting_line(ctx: HookContext) -> Any:
    """SR-116 EX-4: the cards the owner was shown at the end of the last turn are named to the
    agent in one line, so its reply says cards are waiting without restating them or asking
    for prose answers (once per session per set of cards). None when no card waits."""
    from plumb.present.delta import Line

    try:
        from plumb.api import open_core
        from plumb.understand.summary import waiting_line

        text = waiting_line(ctx.root, ctx.session_id, open_core(ctx.root))
    except Exception:  # noqa: BLE001 - an advisory line never fails the prompt hook
        return None
    return Line(text, subject="cards-waiting", state=text) if text else None


def stale_before_line(ctx: HookContext) -> Any:
    """SR-111: the links already stale before the last turn, which a stop that held nothing
    could not tell the agent, listed once per session (marked as it is handed over). None
    when none waits."""
    from plumb.present.delta import Line

    try:
        from plumb.stale import take_before

        text = take_before(ctx.root, ctx.session_id)
    except Exception:  # noqa: BLE001 - an advisory line never fails the prompt hook
        return None
    # oneshot: the queued line was consumed when read, so the budget must never cut it
    return Line(text, oneshot=True) if text else None


def agent_notes(ctx: HookContext) -> list[Any]:
    """SR-173: the warnings the stop hook queued (``stop.queue_notes``), read once."""
    from plumb.present.delta import Line

    path = ctx.session_dir / ctx.session_id / "agent_notes.json"
    notes = read_json(path)
    try:
        path.unlink()
    except OSError:
        pass
    return [Line(str(n), oneshot=True) for n in notes] if isinstance(notes, list) else []


def queued_for_agent(ctx: HookContext) -> list[str]:
    """SR-173, SR-044 EX-1: the agent lines a stop queued for the next prompt (the untraced
    instruction, the waiting lines), read once now, for ``plumb turn end`` whose stdout is
    the agent's channel."""
    from plumb.api import open_core
    from plumb.present.delta import open_emitter

    core = open_core(ctx.root)
    emitter = open_emitter(ctx, "prompt", config=core.config)
    trace = untraced_line(emitter, untraced_queued(ctx, core), core)
    out = emitter.add([*([trace] if trace else []), *agent_notes(ctx)])
    emitter.close()
    return out


def handle(ctx: HookContext, *, verify: Any = LAZY, backend: Any = LAZY) -> HookOutput:
    """Intent translation only, as a deduplicated delta (spec 10, R9, sp5 3).

    Every line goes through the one emitter (``plumb.present.delta``): the
    new or changed relevant records (one line each), the intent-change flags, the compare
    line, escalations and the untraced-change instruction, each once per session per state,
    within ``hooks.prompt_tokens``. They are computed from the records alone and kept
    (``HookContext.keep``); a budget cut, an error or the watchdog prints them. Covering
    tests are not injected: the agent pulls them with ``plumb show``. ``verify`` is accepted
    for the hook interface and unused."""
    del verify
    from plumb.browser.followup import preserve
    from plumb.present.delta import Line, open_emitter

    text = ctx.data.get("prompt")
    text = text if isinstance(text, str) else ""
    if text.strip():
        owned = owner_text(text)
        if not owned.strip():  # SR-112/168: a harness notification: logged, never the owner's
            log_prompt(ctx, text, "notification")
            return HookOutput(text="")
        text = owned
    browser_lines = preserve(ctx)
    digest = log_prompt(ctx, text)
    if prompt_origin(text)[0] != "owner":   # SR-168: logged with its origin, nothing else
        return HookOutput(text="")
    from plumb.api import open_core

    escalations: list[str] = []
    try:
        escalations = escalation_lines(ctx)
    except OSError:
        pass
    core = open_core(ctx.root)
    hooks = core.config.hooks
    stale_turn_start(ctx, core)
    understood = understand_lines(ctx, core, digest, text)
    emitter = open_emitter(ctx, "prompt", config=core.config,
                           cap_lines=int(hooks.prompt_lines))
    trace = untraced_line(emitter, untraced_queued(ctx, core), core)
    tail = [line for line in (trace, cards_waiting_line(ctx), stale_before_line(ctx)) if line]
    tail += agent_notes(ctx)
    # oneshot: escalation_lines advanced the queue offset past them already
    queued = [*browser_lines, *(Line(line, oneshot=True) for line in escalations)]
    ctx.keep(emitter.add([*queued, *tail], commit=False))
    # no soft-budget check before the intent lines: only the watchdog bounds them
    ids, strong = _relevant_ids(core, text) if text.strip() else ([], [])
    index = core.index()
    statuses = core.status(ids) if ids else {}
    records = emitter.add([record_line(i, index, statuses) for i in ids],
                          headers={"records": RECORDS_HEADER})
    injected = [i for i in ids if f"record:{i}" in emitter.emitted]
    ctx.keep([*records, *emitter.add([*queued, *tail], commit=False)])
    intent, flagged = intent_lines(ctx, core, index, statuses, ids, text, digest, backend,
                                   injected)
    if flagged:  # the stop hook shows the owner an intent-change card only when the agent
        # concluded there is a change (sp5 4.2, trigger 1; stop.concluded_flags)
        turn_path = ctx.session_dir / ctx.session_id / "turn.json"
        turn = read_json(turn_path)
        if isinstance(turn, dict):
            write_json_atomic(turn_path, {**turn, "flagged": list(flagged), "flags": flagged})
    hint = escalation_hint(core, index, strong, list(flagged)) if strong else None
    rest = emitter.add([*queued, *intent, *([Line(hint)] if hint else []),
                        *awareness_lines(core, ids), *tail])
    out = [*records, *rest, *understood]
    ctx.keep(out)
    emitter.close()
    return HookOutput(text="\n".join(out))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, backend: Any = LAZY) -> int:
    return run_hook("prompt", lambda ctx: handle(ctx, verify=verify, backend=backend),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("prompt"),
                    watchdog=watchdog, start=start)
