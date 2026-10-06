"""UserPromptSubmit: a compact delta of the relevant records and the intent-change flag
(spec 6.2, ruling R9 context economy).

1. Log the prompt (digest, session, time, text) to ``.plumb/session/prompts.jsonl`` and
   start the turn (``turn.json``). This comes first: ``plumb relay`` relies on it.
2. List the stated records of the previous reply still awaiting the owner, with the relay
   form for this prompt's digest.
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
relay line and the intent-change flags are about this turn (``per_turn``): the relay line
reaches the agent in every turn whose prompt follows a stated set, even when the prompt
repeats earlier words, and every request that may change a confirmed record is flagged,
not only the first one of the session (decision 5, trigger 1). Every
line is an intent-translation line computed from the records alone and kept through a
budget cut (spec 10).

Output is plain text, added to the agent's context. Questions to the owner are left to the
agent, and only on the three triggers.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
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


def log_prompt(ctx: HookContext, text: str) -> str:
    """Append the prompt to the session's prompt log and start the turn. Returns the digest."""
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    _append_jsonl(ctx.session_dir / "prompts.jsonl",
                  {"digest": digest, "session": ctx.session_id, "at": _utc_now(),
                   # R13 Q4: "hook" only from a host's prompt hook; `plumb turn start`
                   # (the agent records the message itself) passes via "turn"
                   "text": text, "via": str(ctx.extra.get("via") or "hook"),
                   # which host's hook logged it: a hook-logged prompt from a host proves
                   # that host's prompt hook runs (approvals.host_logs_prompts)
                   "host": str(ctx.extra.get("host") or "claude-code")})
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


def awaiting_line(core: Any, statuses: Mapping[str, Any], digest: str,
                  stated_path: Path, text: str = "") -> str | None:
    """The relay line for this prompt: the stated records still awaiting the owner, and the
    ``plumb relay`` form for the ones this prompt can confirm (``approvals.owner_scope``,
    the check ``plumb relay`` applies): a bare "ok" lists them all; an ok naming records
    lists only those; a record the prompt objects to is never suggested."""
    from plumb.approvals import owner_scope
    from plumb.normalize import normalize_text

    data = read_json(stated_path)
    if not isinstance(data, dict):
        return None
    items = [item for item in data.get("records") or []
             if isinstance(item, dict) and item.get("id")]
    wanted = [str(item["id"]) for item in items]
    hidden = {str(item["id"]) for item in items if item.get("shown") is False}
    if not wanted:
        return None
    current = core.status([i for i in wanted if i in core.index()])
    pending = [i for i in wanted if i in current and current[i].confirmation != "confirmed"]
    if not pending:
        return None
    short = digest.removeprefix("sha256:")[:12]
    named, objected = owner_scope(normalize_text(text), None,
                                  core.config.approve.affirmations, core.index(),
                                  scope=wanted)
    held = [i for i in pending if i in objected or (named and i not in named)]
    shown = [i for i in pending if i not in hidden and i not in held]
    unshown = [i for i in pending if i in hidden and i not in held]
    line = f"plumb: awaiting confirmation: {', '.join(pending)} | prompt sha256:{short} | "
    against = [i for i in held if i in objected]
    if against:
        line += (f"this prompt objects to or asks to change {', '.join(against)}: do not "
                 "relay them; ")
    if named and [i for i in held if i not in objected]:
        line += (f"the owner's ok names only {', '.join(sorted(named))}: relay only the "
                 "named records; ")
    if shown:
        from plumb.approvals import objection_clauses

        words = ("owner's whole sentence" if objection_clauses(normalize_text(text))
                 else "owner's exact words")
        line += (f"if this prompt affirms them, run plumb relay {' '.join(shown)} --prompt "
                 f"{short} --quote \"<{words}>\"; ")
    if unshown:
        verb = "was" if len(unshown) == 1 else "were"
        pronoun = "it" if len(unshown) == 1 else "them"
        line += (f"{', '.join(unshown)} {verb} not shown in full: relay {pronoun} only if the "
                 f"owner's words name {pronoun}; ")
    return line + "otherwise leave them proposed."


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
    backend = judgment_backend(core, backend)
    if backend is None:
        out.append(Line("plumb: intent check unavailable"))
    else:
        for judgment in backend.intent_change(text, confirmed):
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
    compare = [r.id for r in confirmed if injected is None or r.id in injected]
    if compare:
        out.append(Line("plumb: compare this request with the confirmed examples of "
                        + ", ".join(compare)
                        + "; if it contradicts or extends them, read back the change and ask "
                        "before editing.", subject="compare:" + ",".join(compare),
                        state=",".join(seen_key(index[i], statuses.get(i)) for i in compare)))
    return out, flagged


def handle(ctx: HookContext, *, verify: Any = LAZY, backend: Any = LAZY) -> HookOutput:
    """Intent translation only, as a deduplicated delta (spec 10, R9, sp5 3).

    Every line goes through the one emitter (``plumb.present.delta``): the relay line, the
    new or changed relevant records (one line each), the intent-change flags, the compare
    line, escalations and the untraced-change instruction, each once per session per state,
    within ``hooks.prompt_tokens``. They are computed from the records alone and kept
    (``HookContext.keep``); a budget cut, an error or the watchdog prints them. Covering
    tests are not injected: the agent pulls them with ``plumb show``. ``verify`` is accepted
    for the hook interface and unused."""
    del verify
    from plumb.present.delta import Line, open_emitter

    text = ctx.data.get("prompt")
    text = text if isinstance(text, str) else ""
    digest = log_prompt(ctx, text)
    from plumb.api import open_core

    escalations: list[str] = []
    try:
        escalations = escalation_lines(ctx)
    except OSError:
        pass
    core = open_core(ctx.root)
    hooks = core.config.hooks
    emitter = open_emitter(ctx, "prompt", config=core.config,
                           cap_lines=int(hooks.prompt_lines))
    awaiting = awaiting_line(core, {}, digest, ctx.session_dir / "stated.json", text)
    trace = untraced_line(emitter, untraced_queued(ctx, core), core)
    # per_turn: every affirming prompt is told how to relay, even with the same words
    relay = Line(awaiting, must=True, per_turn=True) if awaiting else None
    tail = [line for line in (trace, relay) if line]
    # oneshot: escalation_lines advanced the queue offset past them already
    queued = [Line(line, oneshot=True) for line in escalations]
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
    rest = emitter.add([*queued, *intent, *([Line(hint)] if hint else []), *tail])
    out = [*records, *rest]
    ctx.keep(out)
    emitter.close()
    return HookOutput(text="\n".join(out))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, backend: Any = LAZY) -> int:
    return run_hook("prompt", lambda ctx: handle(ctx, verify=verify, backend=backend),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("prompt"),
                    watchdog=watchdog, start=start)
