"""Re-check of ``by: auto-model`` approvals (SR-191): the judge model's supported verdict on a
requirement or decision whose premise is the owner's verified words. Written by the worker
only; never an intent, and the premise must still be verified when the entry is read."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plumb.contracts import LogEntry


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why an auto-model entry fails its re-check, or None."""
    payload: Mapping[str, Any] = entry.payload
    if entry.kind != "approval":
        return f"auto-model {entry.kind}: only the owner revokes"
    records, auto = payload.get("records"), payload.get("auto")
    if not isinstance(records, list) or not records or not all(
            isinstance(r, Mapping) and isinstance(r.get("id"), str) and r.get("hash")
            for r in records):
        return "auto-model approval names no record at a version"
    confidence = auto.get("confidence") if isinstance(auto, Mapping) else None
    if not isinstance(auto, Mapping) or not auto.get("model") or isinstance(
            confidence, bool) or not isinstance(confidence, (int, float)) \
            or not 0 <= confidence <= 1:
        return "auto-model approval carries no model or confidence"
    if not all(str(r["id"]).startswith(("SR-", "DEC-")) for r in records):
        return "auto-model approval of an intent, which a model verdict never confirms"
    if core is not None:
        from plumb.capture.triage import _Prompts, premise_problem

        index, prompts = core.index(), _Prompts(core)
        for item in records:
            record = index.get(str(item["id"]))
            if record is not None and record.hash == item["hash"] and (
                    why := premise_problem(prompts, index, record)):
                return f"auto-model approval of {record.id}: {why}"
    return None
