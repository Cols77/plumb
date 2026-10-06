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

Every line is an intent-translation line computed from the records alone and kept through a
budget cut (spec 10).

Output is plain text, added to the agent's context. Questions to the owner are left to the
agent, and only on the three triggers.
"""

from __future__ import annotations

import hashlib
import json
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
SEEN_FILE = "seen.json"


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
                   "text": text, "via": str(ctx.extra.get("via") or "hook")})
    turn_path = ctx.session_dir / ctx.session_id / "turn.json"
    try:  # a new turn: the touched list holds this turn's edits only
        (turn_path.parent / "touched.txt").unlink()
    except OSError:
        pass
    previous = read_json(turn_path)
    asked = previous.get("asked") if isinstance(previous, dict) else None
    write_json_atomic(turn_path, {"turn_start": time.time(), "prompt_digest": digest,
                                  "asked": asked if isinstance(asked, dict) else {}})
    return digest


def _seen_path(ctx: HookContext) -> Path:
    return ctx.session_dir / ctx.session_id / SEEN_FILE


def read_seen(ctx: HookContext) -> dict[str, str]:
    """``{record id: state key}`` of the records this session's agent was already given."""
    data = read_json(_seen_path(ctx))
    seen = data.get("records") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in seen.items()} if isinstance(seen, dict) else {}


def seen_key(record: Any, status: Any) -> str:
    """What makes a record worth injecting again: its content hash and its state."""
    state = status.confirmation if status is not None else "?"
    return f"{record.hash}|{state}"


def delta_lines(index: Mapping[str, Any], statuses: Mapping[str, Any], ids: Sequence[str],
                seen: Mapping[str, str], cap: int,
                budget_chars: int) -> tuple[list[str], list[str]]:
    """``(lines, injected ids)``: one line per relevant record that is new to this session or
    changed since it was injected, in at most ``cap`` lines and ``budget_chars`` characters;
    no line at all when nothing is new. A record cut by the budget is not marked seen, so a
    later prompt can still bring it."""
    fresh = [i for i in ids if seen.get(i) != seen_key(index[i], statuses.get(i))]
    if not fresh:
        return [], []
    header = ("plumb: relevant records, new or changed this session (plumb show <ID> for "
              "examples and tests):")
    lines = [header]
    used = len(header)
    injected: list[str] = []
    for record_id in fresh:
        state = statuses[record_id].confirmation if record_id in statuses else "?"
        line = _clip(f"{record_id} [{state}] {index[record_id].title}")
        if len(lines) >= cap or (injected and used + len(line) > budget_chars):
            break
        lines.append(line)
        used += len(line)
        injected.append(record_id)
    left = [i for i in fresh if i not in injected]
    if left:
        lines.append(_clip(f"plumb: +{len(left)} more relevant: plumb show "
                           + " ".join(left), 160))
    return lines, injected


def write_seen(ctx: HookContext, seen: Mapping[str, str], index: Mapping[str, Any],
               statuses: Mapping[str, Any], injected: Sequence[str]) -> None:
    if not injected:
        return
    merged = dict(seen)
    for record_id in injected:
        merged[record_id] = seen_key(index[record_id], statuses.get(record_id))
    try:
        write_json_atomic(_seen_path(ctx), {"records": merged})
    except OSError:
        pass


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
                  stated_path: Path) -> str | None:
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
    shown = [i for i in pending if i not in hidden]
    unshown = [i for i in pending if i in hidden]
    line = f"plumb: awaiting confirmation: {', '.join(pending)} | prompt sha256:{short} | "
    if shown:
        line += (f"if this prompt affirms them, run plumb relay {' '.join(shown)} --prompt "
                 f"{short} --quote \"<owner's exact words>\"; ")
    if unshown:
        verb = "was" if len(unshown) == 1 else "were"
        pronoun = "it" if len(unshown) == 1 else "them"
        line += (f"{', '.join(unshown)} {verb} not shown in full: relay {pronoun} only if the "
                 f"owner's words name {pronoun}; ")
    return line + "otherwise leave them proposed."


def untraced_line(ctx: HookContext, core: Any) -> str | None:
    """The stop hook's queued untraced change (spec 6.4), delivered once: paths a requirement
    has linked since are dropped, and the note is removed whatever remains."""
    from plumb.trace import trace_instruction, untraced_paths

    note = ctx.session_dir / ctx.session_id / "untraced.json"
    data = read_json(note)
    if data is None:
        return None
    try:
        note.unlink()
    except OSError:
        pass
    paths = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(paths, list):
        return None
    remaining = untraced_paths(core, [str(p) for p in paths])
    return trace_instruction(remaining) if remaining else None


def escalation_lines(ctx: HookContext) -> list[str]:
    """Escalations queued by the cascade since the last print (printed once each)."""
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
                 ) -> tuple[list[str], list[str]]:
    """``(lines, flagged)``: the trigger-1 flags on every relevant confirmed record, and the
    compare line for the confirmed records injected in this prompt (``injected``; all of
    them when None). A record the agent already has gets no repeated compare line (R9)."""
    confirmed = [index[i] for i in ids if statuses[i].confirmation == "confirmed"]
    out: list[str] = []
    flagged: list[str] = []
    if not confirmed:
        return out, flagged
    backend = judgment_backend(core, backend)
    if backend is None:
        out.append("plumb: intent check unavailable")
    else:
        for judgment in backend.intent_change(text, confirmed):
            if judgment.verdict != "change":
                continue
            flagged.append(judgment.subject)
            out.append(f"plumb: this may change {judgment.subject} (confirmed). If it "
                       "does, read back the change and ask before editing; if not, "
                       "proceed.")
            _append_jsonl(ctx.session_dir / "intent_flags.jsonl",
                          {"at": _utc_now(), "session": ctx.session_id,
                           "prompt_digest": digest, "subject": judgment.subject,
                           "confidence": judgment.confidence,
                           "backend": judgment.backend, "tier": judgment.tier})
    compare = [r.id for r in confirmed if injected is None or r.id in injected]
    if compare:
        out.append("plumb: compare this request with the confirmed examples of "
                   + ", ".join(compare)
                   + "; if it contradicts or extends them, read back the change and ask "
                   "before editing.")
    return out, flagged


def handle(ctx: HookContext, *, verify: Any = LAZY, backend: Any = LAZY) -> HookOutput:
    """Intent translation only, as a deduplicated delta (spec 10, R9).

    The relay line, the new or changed relevant records (one line each), the intent-change
    flags, the compare line and the escalation hint are computed from the records alone and
    kept (``HookContext.keep``); a budget cut, an error or the watchdog prints them. Covering
    tests are not injected: the agent pulls them with ``plumb show``. ``verify`` is accepted
    for the hook interface and unused."""
    del verify
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
    awaiting = awaiting_line(core, {}, digest, ctx.session_dir / "stated.json")
    trace = untraced_line(ctx, core)
    tail = [line for line in (trace, awaiting) if line]
    ctx.keep([*escalations, *tail])
    # no soft-budget check before the intent lines: only the watchdog bounds them
    ids, strong = _relevant_ids(core, text) if text.strip() else ([], [])
    index = core.index()
    statuses = core.status(ids) if ids else {}
    hooks = core.config.hooks
    seen = read_seen(ctx)
    records, injected = delta_lines(index, statuses, ids, seen, int(hooks.prompt_lines),
                                    int(hooks.prompt_tokens) * CHARS_PER_TOKEN)
    ctx.keep([*records, *escalations, *tail])  # a slow intent check still leaves the delta
    intent, flagged = intent_lines(ctx, core, index, statuses, ids, text, digest, backend,
                                   injected)
    hint = escalation_hint(core, index, strong, flagged) if strong else None
    middle = [*intent, *([hint] if hint else [])]
    out = [*records, *escalations, *middle, *tail]
    ctx.keep(out)
    write_seen(ctx, seen, index, statuses, injected)
    return HookOutput(text="\n".join(out))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, backend: Any = LAZY) -> int:
    return run_hook("prompt", lambda ctx: handle(ctx, verify=verify, backend=backend),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("prompt"),
                    watchdog=watchdog, start=start)
