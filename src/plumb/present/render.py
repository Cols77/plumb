"""The output contract every host renders (sp5 4, 9): the status card, one owner-facing line,
in the status line and as the first line of the end-of-turn summary. It renders a snapshot
(``StatusSnapshot`` or its ``status.json`` mapping) and recomputes nothing (SR-061).

Standard library only: the status line imports this module on every refresh.
"""

from __future__ import annotations

import dataclasses
import unicodedata
from collections.abc import Mapping
from typing import Any

STATES = ("regression", "failing", "awaits you", "drift", "aligned")
GLYPHS = {"aligned": "✓", "awaits you": "●", "drift": "▲", "failing": "✗",
          "regression": "✗"}
SUMMARY_WIDTH = 40


def _data(snapshot: Any) -> Mapping[str, Any]:
    if dataclasses.is_dataclass(snapshot) and not isinstance(snapshot, type):
        return dataclasses.asdict(snapshot)
    return snapshot if isinstance(snapshot, Mapping) else {}


def _int(data: Mapping[str, Any], key: str) -> int:
    try:
        return int(data.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def card_state(snapshot: Any) -> str:
    """regression > failing > awaits you > drift > aligned (sp5 4.1)."""
    data = _data(snapshot)
    tests = data.get("tests")
    if tests == "regression" or data.get("regressions"):
        return "regression"
    if tests == "failing":
        return "failing"
    if _int(data, "ask") > 0:   # SR-263 EX-6: records the judge is checking are not the owner's
        return "awaits you"
    if _int(data, "stale_links") or _int(data, "dangling_links"):
        return "drift"
    return "aligned"


def to_ascii(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text))
    return folded.encode("ascii", "ignore").decode("ascii")


def clip(text: str, width: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


def status_card(snapshot: Any, *, ascii: bool = False) -> str:
    """``plumb ✓ aligned · "add multiply next to add" · SR 12/14 ok (2 judge-approved) · 2 waiting on
    a judge``; with ``ascii`` the glyphs become words and ``|`` separators."""
    data = _data(snapshot)
    state = card_state(data)
    total = _int(data, "requirements_total")
    confirmed = _int(data, "requirements_confirmed")
    by = data.get("confirmed_by") if isinstance(data.get("confirmed_by"), Mapping) else {}
    judged = _int(by, "auto-jev") + _int(by, "auto-model")
    parts = [state]
    summary = clip(data.get("intent_summary") or "", SUMMARY_WIDTH)
    if summary:
        parts.append(f'"{summary}"')
    notes = ([f"{judged} judge-approved"] if judged else [])   # SR-251
    parts.append(f"SR {confirmed}/{total} ok" + (f" ({', '.join(notes)})" if notes else ""))
    proposed = _int(data, "proposed")
    if proposed:
        parts.append(f"{proposed} waiting on a judge")
    stale = _int(data, "stale_links")
    if stale:
        parts.append(f"{stale} stale")
    failing = len(data.get("failing") or ())
    if state in ("failing", "regression") and failing:
        parts.append(f"{failing} failing")
    ask = _int(data, "ask")
    if ask:
        parts.append(f"{ask} question" + ("s" if ask > 1 else ""))
    if data.get("full_pending"):
        parts.append("full pending")
    if data.get("auto_approve") == "suspended":
        parts.append("auto-approve suspended")
    parts += overlap_parts(data, ascii=ascii)
    if ascii:
        return to_ascii("plumb | " + " | ".join(parts))
    return f"plumb {GLYPHS[state]} " + " · ".join(parts)


def overlap_parts(data: Mapping[str, Any], *, ascii: bool = False) -> list[str]:
    """sp6 8.3, 9.4: ``1 also changed on feat-x`` (``overlap 1 (feat-x)`` in ASCII) and
    ``1 conflict awaits you``; nothing when zero."""
    from plumb.present import owner_text as text

    parts: list[str] = []
    overlaps = _int(data, "overlaps")
    if overlaps:
        labels = ", ".join(str(b) for b in data.get("overlap_labels") or ()) or "elsewhere"
        parts.append((text.OVERLAP_CARD_ASCII if ascii else text.OVERLAP_CARD)
                     .format(n=overlaps, labels=labels))
    conflicts = _int(data, "conflicts")
    if conflicts:
        parts.append((text.CONFLICTS_CARD if conflicts == 1 else text.CONFLICTS_CARD_PLURAL)
                     .format(n=conflicts))
    return parts
