"""Re-check of the judge's approvals after a question round (SR-248, SR-251, DEC-141).

``by: auto-model``: the judge model said the intent is clear (``clear: true``) after the
owner answered its questions; its confidence is logged and never compared to a bar. Written
by the worker only, for any judged kind. ``cited_answers_problem`` is the answer check both
``auto-model`` and an answer-cited ``auto-jev`` pass, in log order (``confirm.checked_entries``):
each cited answer is a question-tool answer logged before the approval, naming each record
it approves at that version."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from iaso.contracts import LogEntry


def problem(entry: LogEntry, core: Any) -> str | None:
    """Why an auto-model entry fails its re-check on its own payload, or None."""
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
    if auto.get("clear") is not True:
        return "auto-model approval without the judge model saying the intent is clear"
    if not payload.get("answers"):
        return "auto-model approval without a question round (it cites no answer)"
    return None


def cited_answers_problem(payload: Mapping[str, Any], logged: Mapping[str, Mapping[str, Any]],
                          by: str, confirmed: Collection[tuple[str, str]] = ()
                          ) -> str | None:
    """Why the answers an approval cites do not carry it, or None. ``logged``: digest ->
    payload of the question-answer entries (and the read path's ``pre-intent`` entries,
    ``via: read``) logged before the approval; ``confirmed``: the ``(id, hash)`` pairs
    approved before it. An answer carries the record at the version asked about or at a
    later wording of a version never confirmed (SR-209 EX-4), never an edit of a confirmed
    one (SR-248 EX-9)."""
    from iaso.understand.premise import ANSWER_VIA, carries

    cited = payload.get("answers")
    if not isinstance(cited, list) or not cited:
        return f"{by} approval cites no answer of the owner"
    asked: set[tuple[str, str]] = set()
    for digest in cited:
        answer = logged.get(str(digest))
        if answer is None or answer.get("via") not in ANSWER_VIA.values() \
                or not isinstance(answer.get("asked"), Mapping):
            return f"{by} approval cites an answer that is no earlier question-tool answer"
        asked |= {(str(r.get("id")), str(r.get("hash")))
                  for r in answer["asked"].get("records") or () if isinstance(r, Mapping)}
    for item in payload.get("records") or ():
        if not isinstance(item, Mapping):
            continue
        rid, current = str(item.get("id")), str(item.get("hash"))
        done = {h for i, h in confirmed if i == rid}
        if not any(i == rid and carries(h, current, done) for i, h in asked):
            return (f"{by} approval of {rid}: no cited answer was asked about it at that "
                    "version or an unconfirmed earlier one")
    return None
