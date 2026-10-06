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
GROUP_ORDER = ("agent-relayed", "auto-jev", "owner", "import")
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
    ``host: cli``."""
    if _marks_self_recorded(payload):
        return True
    digest = payload.get("prompt_digest")
    if not isinstance(digest, str):
        return False
    return (_marks_self_recorded(prompt_events.get(digest))
            or _marks_self_recorded(prompt_log.get(digest)))


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
        if by == "auto-jev":
            for key in ("score", "confidence", "model_version", "backend", "claim_kind",
                        "calibration"):
                row[key] = payload.get(key)
        if isinstance(payload.get("triage"), Mapping):
            row["triage"] = str(payload["triage"].get("group") or "")
        if isinstance(payload.get("set"), Mapping):
            row["set"] = str(payload["set"].get("anchor") or "")
        if isinstance(payload.get("upstream"), Mapping):
            row["consent"] = payload["upstream"].get("consent_path")
        rows.append(row)
    rank = {name: n for n, name in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda r: rank.get(r["by"], len(GROUP_ORDER)))  # stable: log order kept
    return rows


def glance_line(row: Mapping[str, Any]) -> str:
    """One line per row, ending with the revoke command for an approval."""
    what = ", ".join(row["records"] + [f"trace.exempt {' '.join(row['exempt'])}"]
                     if row["exempt"] else row["records"]) or "(nothing)"
    kind = "" if row["kind"] == "approval" else "revocation "
    by = row["by"]
    if by == "agent-relayed":
        line = (f"  {kind}AGENT-RELAYED {what} quote \"{row['quote']}\" prompt "
                f"{str(row['prompt_digest'])[:19]}")
        if row.get("self_recorded"):
            line += " (self-recorded message: no prompt hook logged it)"
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
