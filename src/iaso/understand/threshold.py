"""The reader's threshold (SR-101 EX-14): 0.9 (``understand.reader_threshold_start``) until
twenty labelled answers are on file, then the lowest confidence at and above which the owner
agreed with every reader answer.

The labels, all from the committed log (nothing here is a model call):
- ``approval`` ``by: owner-words``: the owner agreed (a yes at the reader's confidence), unless
  an ``undone`` revocation of the same record version followed;
- ``rejection`` ``by: owner-words`` with reason ``capture-error`` (the ``misread`` rejection):
  the owner disagreed;
- ``trial`` entries: each ``answers`` item with ``answer`` yes/no and the reader's
  ``confidence``."""

from __future__ import annotations

from typing import Any

MIN_LABELS = 20


def _number(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def labels(core: Any) -> list[tuple[float, bool]]:
    """``(reader confidence, the owner agreed)`` for every labelled reader answer."""
    out: list[tuple[float, bool]] = []
    undone: set[tuple[str, str]] = set()
    entries = list(core.events())
    for entry in entries:
        if entry.kind == "revocation" and entry.payload.get("by") == "undone":
            undone |= {(str(r.get("id")), str(r.get("hash")))
                       for r in entry.payload.get("records") or () if isinstance(r, dict)}
    for entry in entries:
        payload = entry.payload
        confidence = _number(payload.get("confidence"))
        if entry.kind == "approval" and payload.get("by") == "owner-words":
            if confidence is None:
                continue
            records = [r for r in payload.get("records") or () if isinstance(r, dict)]
            gone = any((str(r.get("id")), str(r.get("hash"))) in undone for r in records)
            out.append((confidence, payload.get("label") != "no" and not gone))
        elif entry.kind == "rejection" and payload.get("by") == "owner-words":
            if confidence is not None and payload.get("reason") == "capture-error":
                out.append((confidence, False))
        elif entry.kind == "trial":
            for item in payload.get("answers") or ():
                if not isinstance(item, dict) or item.get("answer") not in ("yes", "no"):
                    continue
                seen = _number(item.get("confidence"))
                if seen is not None:
                    out.append((seen, item["answer"] == "yes"))
    return out


def threshold_from(labelled: list[tuple[float, bool]], start: float) -> float:
    """The lowest confidence at and above which every labelled answer was agreed with."""
    if len(labelled) < MIN_LABELS:
        return start
    worst = max((c for c, ok in labelled if not ok), default=None)
    agreed = [c for c, ok in labelled if ok and (worst is None or c > worst)]
    return min(agreed) if agreed else 1.0


def reader_threshold(core: Any) -> float:
    return threshold_from(labels(core), float(core.config.understand.reader_threshold_start))
