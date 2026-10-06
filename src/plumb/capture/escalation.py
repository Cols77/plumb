"""Escalation to an up-front spec, suggested on the concept's triggers, once (sp2 6.1,
SR-036).

A suggestion is one line a hook prints (``plumb: consider an up-front spec: touches 2
features (FEAT-001, FEAT-003); the owner decides``); it is never a question by itself
(decision 5). ``plumb escalate decline`` appends an ``escalation-declined`` event, after
which the same trigger is not suggested again for the same intent: relayed with the owner's
own words, or from the owner's terminal through ``approvals.require_owner``.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import DiffStats, EscalationSuggestion, LogEntry

if TYPE_CHECKING:
    from plumb.api import Core

TRIGGERS = ("size", "contradiction", "shared", "irreversible", "decisions", "diff")
_ID = re.compile(r"(?<![A-Za-z0-9-])((?:INT|SR|DEC|FEAT)-\d{3,}|NC-\d{4,})(?![0-9])")
STRONG = 1.0


def _glob(pattern: str, path: str) -> bool:
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    return False


def matched_ids(core: Core, prompt: str | None, matched: Sequence[str]) -> list[str]:
    """The records a request is about: the given ones, else the IDs it names and the records
    it matches strongly."""
    index = core.index()
    if matched:
        return [i for i in matched if i in index]
    if not prompt:
        return []
    named = [i for i in _ID.findall(prompt) if i in index]
    strong = [i for i, score in core.relevant(prompt, 8) if score >= STRONG and i not in named]
    return named + strong


def intent_of(core: Core, ids: Sequence[str]) -> str | None:
    """The INT the request is about: named, or the one its records derive from, or the
    latest INT."""
    index = core.index()
    for record_id in ids:
        if record_id.startswith("INT-"):
            return record_id
    for record_id in ids:
        for link in index[record_id].links if record_id in index else ():
            if link.kind == "derives_from" and str(link.target.record or "").startswith("INT-"):
                return link.target.record
    intents = sorted((i for i in index if i.startswith("INT-")), key=lambda i: int(i[4:]))
    return intents[-1] if intents else None


def declined(entries: Iterable[LogEntry]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for entry in entries:
        if entry.kind != "escalation-declined":
            continue
        intent = str(entry.payload.get("intent") or "none")
        for trigger in entry.payload.get("triggers") or TRIGGERS:
            out.add((intent, str(trigger)))
    return out


def set_approved(core: Core, intent: str | None) -> bool:
    """Whether ``intent`` is an escalated set whose approval stands."""
    if not intent:
        return False
    from plumb.capture.spec import set_state

    return set_state(core, intent) == "approved"


def _feature_of(index: Mapping[str, Any], record_id: str) -> str | None:
    record = index.get(record_id)
    if record is None:
        return None
    if record.kind == "feature":
        return record.id
    feature = record.fields.get("feature")
    return str(feature) if feature else None


def escalation(core: Core, *, prompt: str | None = None, matched: Sequence[str] = (),
               diff: DiffStats | None = None, planned_requirements: Sequence[str] = (),
               planned_features: Sequence[str] = (), backend: Any = None,
               intent: str | None = None) -> list[EscalationSuggestion]:
    """Suggestions for the triggers of sp2 6.1, minus the ones the owner declined."""
    config = core.config.escalation
    index = core.index()
    ids = matched_ids(core, prompt, matched)
    intent = intent or intent_of(core, ids)
    found: list[tuple[str, str]] = []

    requirements = sorted({i for i in ids if index[i].kind == "requirement"}
                          | set(planned_requirements))
    features = sorted({f for i in ids if (f := _feature_of(index, i))} | set(planned_features))
    if len(requirements) > config.max_requirements:
        found.append(("size", f"changes {len(requirements)} requirements "
                              f"({', '.join(requirements[:5])})"))
    elif len(features) > config.max_features:
        found.append(("size", f"touches {len(features)} features ({', '.join(features)})"))

    if prompt:
        from plumb.capture.flags import intent_flags

        contradicted = [f.record for f in intent_flags(core, prompt, ids, backend)
                        if f.kind == "contradicts"]
        if contradicted:
            found.append(("contradiction", "contradicts confirmed "
                                           + ", ".join(sorted(set(contradicted)))))

    paths = list(diff.paths) if diff is not None else []
    shared_globs = tuple(config.shared_globs) + tuple(core.config.verify.infra_globs)
    shared = [p for p in paths if any(_glob(g, p) for g in shared_globs)]
    if shared:
        found.append(("shared", "touches shared surfaces: " + ", ".join(shared[:4])))

    words = [w for w in config.irreversible if "/" not in w and "*" not in w]
    globs = [w for w in config.irreversible if "/" in w or "*" in w]
    hits: list[str] = []
    if prompt:
        lowered = prompt.lower()
        hits = [w for w in words if re.search(rf"(?<![\w]){re.escape(w.lower())}(?![\w])",
                                              lowered)]
    hits += [p for p in paths if any(_glob(g, p) for g in globs)]
    if hits:
        found.append(("irreversible", "hard to undo: " + ", ".join(hits[:4])))

    related = set(ids) | ({intent} if intent else set())
    statuses = core.status()
    open_decisions = sorted(
        r.id for r in index.values() if r.kind == "decision"
        and r.fields.get("matters") is True and statuses[r.id].confirmation != "confirmed"
        and (r.id in related or any(link.target.record in related for link in r.links
                                    if link.kind in ("derives_from", "decides"))))
    if len(open_decisions) >= 2:
        found.append(("decisions", f"{len(open_decisions)} decisions that matter are "
                                   f"unconfirmed ({', '.join(open_decisions[:4])})"))

    if diff is not None and (diff.lines > config.diff_lines or diff.files > config.diff_files) \
            and not set_approved(core, intent):
        size = (f"{diff.lines} changed lines" if diff.lines > config.diff_lines
                else f"{diff.files} files")
        found.append(("diff", f"the diff passes {size} without an approved up-front spec"))

    skip = declined(core.events())
    key = intent or "none"
    out: list[EscalationSuggestion] = []
    for trigger, reason in found:
        if (key, trigger) in skip:
            continue
        out.append(EscalationSuggestion(
            trigger=trigger, reason=reason, intent=intent,  # type: ignore[arg-type]
            line=f"plumb: consider an up-front spec: {reason}; the owner decides"))
    return out


def decline(core: Core, *, intent: str | None, triggers: Sequence[str] = (),
            prompt: str | None = None, quote: str | None = None) -> LogEntry:
    """Record that the owner declined the suggestion: relayed with the owner's own words
    (``prompt`` and ``quote``), or from the owner's terminal."""
    from plumb.approvals import (
        Refused,
        find_prompt,
        quote_in_prompt,
        require_owner,
    )
    from plumb.normalize import normalize_text, sha256_text

    bad = [t for t in triggers if t not in TRIGGERS]
    if bad:
        from plumb.capture.records import CaptureError

        raise CaptureError(f"unknown trigger {bad[0]} (one of {', '.join(TRIGGERS)})")
    if intent is not None and intent not in core.index():
        from plumb.capture.records import CaptureError

        raise CaptureError(f"no record {intent}")
    payload: dict[str, Any] = {"intent": intent, "triggers": list(triggers) or list(TRIGGERS)}
    if prompt is not None or quote is not None:
        if not prompt or not quote:
            raise Refused("a relayed decline needs --prompt and --quote (the owner's words)")
        entry = find_prompt(core, prompt)
        normalized = normalize_text(quote)
        if not quote_in_prompt(normalized, normalize_text(str(entry["text"]))):
            raise Refused("the quote is not a verbatim part of that prompt (whole words)")
        digest = str(entry["digest"])
        known = {e.payload.get("digest") for e in core.events() if e.kind == "prompt"}
        if digest not in known:
            core.log_append("events", "prompt", {"digest": digest,
                                                 "session": entry.get("session"),
                                                 "at": entry.get("at")})
        payload.update({"by": "agent-relayed", "prompt_digest": digest, "quote": normalized,
                        "quote_digest": sha256_text(normalized),
                        "self_recorded": entry.get("via") != "hook"})
    else:
        require_owner("escalate decline", "record that you decline an up-front spec for "
                      f"{intent or 'this work'} (by: owner)?")
        payload["by"] = "owner"
    return core.log_append("events", "escalation-declined", payload)
