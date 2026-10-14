"""The glance: approvals and revocations added in the range, for a quick owner look (sp3 3.2).

Agent-relayed approvals carry the owner's quote and the prompt digest (R2); auto-jev
approvals carry the score, the confidence label and the model version (R8 B); a relay that
rests on a message the agent recorded itself (a host without a prompt hook) is labelled
"self-recorded message" (R13 Q4). Each approval row ends with its revoke command. The glance
is never a question and never changes the exit code.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

# Rows in this order: what the owner did not type in their own terminal comes first.
GROUP_ORDER = ("agent-relayed", "auto-jev", "owner-words", "owner", "import")
SELF_RECORDED_VIA = frozenset({"turn", "turn-start", "cli", "agent", "self"})
SELF_RECORDED_HOSTS = frozenset({"cli"})


def _marks_self_recorded(item: Mapping[str, Any] | None) -> bool:
    if not isinstance(item, Mapping):
        return False
    if item.get("self_recorded") is True:
        return True
    return (str(item.get("via") or "") in SELF_RECORDED_VIA
            or str(item.get("host") or "") in SELF_RECORDED_HOSTS)


def _prompt_log(core: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    try:
        with open(core.paths.prompts, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, Mapping) and isinstance(item.get("digest"), str):
                    out.setdefault(item["digest"], item)
    except OSError:
        pass
    return out


def self_recorded(payload: Mapping[str, Any], prompt_events: Mapping[str, Mapping[str, Any]],
                  prompt_log: Mapping[str, Mapping[str, Any]]) -> bool:
    """Whether a relayed approval rests on a message the agent recorded itself.

    The convention, read in three places so any writer can state it: the approval payload,
    the committed ``prompt`` event it cites, or the session's prompt-log line, carrying
    ``self_recorded: true``, ``via`` naming a self-recording path (``turn``, ``cli``) or
    ``host: cli``. A relay that states it (``plumb relay`` writes ``self_recorded`` into the
    digest-protected payload) is read through ``confirm.is_self_recorded``, the one test every
    surface labels by; the prompt fallbacks serve only approvals written without the key."""
    if "self_recorded" in payload:
        from plumb.confirm import is_self_recorded

        return is_self_recorded(payload)
    if _marks_self_recorded(payload):
        return True
    digest = payload.get("prompt_digest")
    if not isinstance(digest, str):
        return False
    return (_marks_self_recorded(prompt_events.get(digest))
            or _marks_self_recorded(prompt_log.get(digest)))


MESSAGE_CHARS = 240


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MESSAGE_CHARS else text[: MESSAGE_CHARS - 3] + "..."


def _message(payload: Mapping[str, Any],
             prompt_log: Mapping[str, Mapping[str, Any]],
             core: Any = None) -> dict[str, Any]:
    """The owner's whole logged message beside the quote that was recorded, and whether the
    approval itself says the message also objected to or asked to change something (an older
    relayed approval wrote ``prompt_objects``). The text is in the session's prompt log while
    it exists. No rule reads the words here (INT-029): the glance only shows them."""
    from plumb.normalize import normalize_text

    item = prompt_log.get(str(payload.get("prompt_digest") or ""))
    raw = item.get("text") if isinstance(item, Mapping) else None
    text = normalize_text(raw) if isinstance(raw, str) else None
    return {"prompt_objects": payload.get("prompt_objects") is True, "prompt_text": text}


AUTO_KEYS = ("score", "model_version", "backend", "claim_kind", "calibration")


def auto_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The score, confidence label, model version, backend, claim kind and calibration of an
    ``auto-jev`` approval, whichever shape wrote it: CAPTURE's writer
    (``capture.autoapprove.gate``) nests them under ``payload["auto"]``, with the numeric
    confidence in ``confidence`` and the label in ``confidence_label``; sp2 8.2 shows them at
    the top level. The one place the glance reads them, so the two never disagree."""
    nested = payload.get("auto")
    source: Mapping[str, Any] = nested if isinstance(nested, Mapping) else payload
    out = {key: source.get(key) for key in AUTO_KEYS}
    label = source.get("confidence_label")
    out["confidence"] = label if label is not None else source.get("confidence")
    return out


def _ids(payload: Mapping[str, Any]) -> list[str]:
    return [str(r.get("id")) for r in payload.get("records") or [] if isinstance(r, Mapping)]


def glance_rows(core: Any, base_digests: Iterable[str]) -> list[dict[str, Any]]:
    """Every ``approval`` and ``revocation`` event not present at the merge base, grouped."""
    known = set(base_digests)
    events = core.events()
    prompt_events = {str(e.payload.get("digest")): e.payload for e in events
                     if e.kind == "prompt"}
    prompt_log: dict[str, Mapping[str, Any]] | None = None
    rows: list[dict[str, Any]] = []
    for entry in events:
        if entry.kind not in ("approval", "revocation") or entry.digest in known:
            continue
        payload: Mapping[str, Any] = entry.payload
        by = str(payload.get("by"))
        ids = _ids(payload)
        row: dict[str, Any] = {
            "kind": entry.kind, "by": by, "at": entry.at, "records": ids,
            "exempt": [str(g) for g in payload.get("exempt") or []],
            "quote": payload.get("quote"), "prompt_digest": payload.get("prompt_digest"),
            "marker": entry.marker, "digest": entry.digest,
            "revoke": (f"plumb revoke {' '.join(ids)}"
                       if entry.kind == "approval" and ids else None),
            "self_recorded": False,
        }
        if by == "agent-relayed":
            if prompt_log is None:
                prompt_log = _prompt_log(core)
            row["self_recorded"] = self_recorded(payload, prompt_events, prompt_log)
            row.update(_message(payload, prompt_log, core))
        if by == "auto-jev":
            row.update(auto_fields(payload))
        if isinstance(payload.get("triage"), Mapping):
            row["triage"] = str(payload["triage"].get("group") or "")
        if isinstance(payload.get("set"), Mapping):
            row["set"] = str(payload["set"].get("anchor") or "")
        if isinstance(payload.get("upstream"), Mapping):
            row["consent"] = payload["upstream"].get("consent_path")
        rows.append(row)
    rows += _renumber_rows(core, known)
    rank = {name: n for n, name in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda r: rank.get(r["by"], len(GROUP_ORDER)))  # stable: log order kept
    return rows


def _renumber_rows(core: Any, known: set[str]) -> list[dict[str, Any]]:
    """R17: the approvals a renumber in the range carried, for the owner's glance."""
    if not any(e.kind == "renumber" for e in core.events()):
        return []
    from plumb.ids.aliases import glance_rows

    return glance_rows(core, known)


def glance_line(row: Mapping[str, Any]) -> str:
    """One line per row, ending with the revoke command for an approval."""
    if row.get("kind") == "renumber":
        from plumb.present.owner_text import CARRIED_GLANCE

        return CARRIED_GLANCE.format(old=row["from"], new=row["to"], title=row["title"])
    what = ", ".join(row["records"] + [f"trace.exempt {' '.join(row['exempt'])}"]
                     if row["exempt"] else row["records"]) or "(nothing)"
    kind = "" if row["kind"] == "approval" else "revocation "
    by = row["by"]
    if by == "agent-relayed":
        line = (f"  {kind}AGENT-RELAYED {what} quote \"{row['quote']}\" prompt "
                f"{str(row['prompt_digest'])[:19]}")
        if row.get("self_recorded"):
            line += " (self-recorded message: no prompt hook logged it)"
        if row.get("prompt_objects"):
            line += " (the same message also objects or asks for a change)"
        if row.get("prompt_text") and row["prompt_text"] != row.get("quote"):
            line += f" message \"{_clip(str(row['prompt_text']))}\""
    elif by == "auto-jev":
        line = (f"  {kind}AUTO-JEV {what} score {row.get('score')} ({row.get('confidence')}) "
                f"model {row.get('model_version')} prompt {str(row['prompt_digest'])[:19]}")
    else:
        line = f"  {kind}{by} {what}"
        if row.get("triage"):
            line += f" (triage group {row['triage']})"
        if row.get("set"):
            line += f" (set approval of {row['set']})"
        if row.get("consent"):
            line += f" (consent {row['consent']})"
    line += f" at {row['at']}"
    if row.get("revoke"):
        line += f" | {row['revoke']}"
    return line
