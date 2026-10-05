"""UserPromptSubmit: relevant records, their tests and the intent-change flag (spec 6.2).

1. Log the prompt (digest, session, time, text) to ``.plumb/session/prompts.jsonl`` and
   start the turn (``turn.json``). This comes first: ``plumb relay`` relies on it.
2. Print the relevant records (named IDs first), their examples and covering tests, in at
   most ``hooks.prompt_lines`` lines.
3. Flag a possible intent change on a confirmed record (``JudgmentBackend``), and ask the
   agent to compare the request with the confirmed examples it was given.
4. List the stated records of the previous reply still awaiting the owner, with the relay
   form for this prompt's digest.
5. Print queued escalations and the escalation hint (SHOULD items).

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
from plumb.hosts.claude_code.providers import LAZY, judgment_backend, verify_api

STRONG_MATCH = 1.0
EXAMPLES_PER_RECORD = 3


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
                   "text": text})
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


def _example_line(example: Any) -> str:
    if example.given or example.when or example.then:
        text = f"given {example.given}, when {example.when}, then {example.then}"
    else:
        text = example.criterion
    return "  " + _clip(f"{example.id}: {text}", 98)


def record_lines(index: Mapping[str, Any], statuses: Mapping[str, Any], ids: Sequence[str],
                 tests: Mapping[str, Sequence[str]] | None, cap: int) -> list[str]:
    """Header plus, per record, its state, examples and covering tests; at most ``cap``."""
    lines = ["plumb: relevant records (state; examples; covering tests):"]
    for position, record_id in enumerate(ids):
        record = index[record_id]
        left = cap - len(lines)
        later = len(ids) - position - 1  # keep one header line for each later record
        if left <= 0:
            break
        state = statuses[record_id].confirmation if record_id in statuses else "?"
        lines.append(_clip(f"{record_id} [{state}] {record.title}"))
        room = left - 1 - later
        node_ids = list(tests.get(record_id, ())) if tests else []
        detail: list[str] = [_example_line(e) for e in record.examples[:EXAMPLES_PER_RECORD]]
        if node_ids:
            detail.append("  " + _clip("tests: " + ", ".join(node_ids), 98))
        if room <= 0:
            continue
        if len(detail) > room:
            # keep the tests line when present, then as many examples as fit
            detail = (detail[: room - 1] + detail[-1:]) if node_ids and room > 1 else \
                detail[:room]
        lines.extend(detail)
    return lines[:cap] if len(lines) > 1 else []


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
    wanted = [str(item.get("id")) for item in data.get("records") or []
              if isinstance(item, dict) and item.get("id")]
    if not wanted:
        return None
    current = core.status([i for i in wanted if i in core.index()])
    pending = [i for i in wanted if i in current and current[i].confirmation != "confirmed"]
    if not pending:
        return None
    short = digest.removeprefix("sha256:")[:12]
    ids = " ".join(pending)
    return (f"plumb: awaiting confirmation: {', '.join(pending)} | prompt sha256:{short} | "
            f"if this prompt affirms them, run plumb relay {ids} --prompt {short} --quote "
            "\"<owner's exact words>\"; otherwise leave them proposed.")


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


def handle(ctx: HookContext, *, verify: Any = LAZY, backend: Any = LAZY) -> HookOutput:
    text = ctx.data.get("prompt")
    text = text if isinstance(text, str) else ""
    digest = log_prompt(ctx, text)
    from plumb.api import open_core

    out: list[str] = []
    try:
        out.extend(escalation_lines(ctx))
    except OSError:
        pass
    core = open_core(ctx.root)
    ctx.deadline.check("open core")
    ids, strong = _relevant_ids(core, text) if text.strip() else ([], [])
    index = core.index()
    statuses = core.status(ids) if ids else {}
    ctx.deadline.check("relevant records")
    if ids:
        verify = verify_api(core, verify)
        tests = verify.tests_for(ids) if verify is not None else None
        out[:0] = record_lines(index, statuses, ids, tests, int(core.config.hooks.prompt_lines))
        if verify is None:
            out.append("plumb: verification unavailable")
    confirmed = [index[i] for i in ids if statuses[i].confirmation == "confirmed"]
    flagged: list[str] = []
    if confirmed:
        ctx.deadline.check("intent check")
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
        out.append("plumb: compare this request with the confirmed examples of "
                   + ", ".join(r.id for r in confirmed)
                   + "; if it contradicts or extends them, read back the change and ask "
                   "before editing.")
    hint = escalation_hint(core, index, strong, flagged) if strong else None
    if hint:
        out.append(hint)
    awaiting = awaiting_line(core, statuses, digest, ctx.session_dir / "stated.json")
    if awaiting:
        out.append(awaiting)
    return HookOutput(text="\n".join(out))


def main(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
         root: Path | str | None = None, watchdog: bool = False, start: float | None = None,
         verify: Any = LAZY, backend: Any = LAZY) -> int:
    return run_hook("prompt", lambda ctx: handle(ctx, verify=verify, backend=backend),
                    stdin=stdin, stdout=stdout, root=root, budget_ms=hook_budget("prompt"),
                    watchdog=watchdog, start=start)
