"""The output contract every host renders (sp5 4, 9): the status card and the intent card.

- ``status_card``: one owner-facing line, in the status line and as the first line of the
  end-of-turn summary. It renders a snapshot (``StatusSnapshot`` or its ``status.json``
  mapping) and recomputes nothing (SR-061).
- ``intent_card``: the four-line card of one record, shown only when it matters (SR-062).
  A card shows its record in full (nothing is clipped), so it is the "shown" form of the
  stated set: a bare "ok" may confirm a record only once its card was shown.

Standard library only: the status line imports this module on every refresh.
"""

from __future__ import annotations

import dataclasses
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import IntentCardData

STATES = ("regression", "failing", "awaits you", "drift", "aligned")
GLYPHS = {"aligned": "✓", "awaits you": "●", "drift": "▲", "failing": "✗",
          "regression": "✗"}
SUMMARY_WIDTH = 40
KINDS = {"INT": "Intent", "SR": "Requirement", "DEC": "Question", "FEAT": "Feature",
         "NC": "Nonconformance"}
TEST_MARKS = {"passing": ("✓", "ok"), "failing": ("✗", "x"), "not run": ("○", "-"),
              "not yet passing": ("◌", "~"), "regression": ("✗", "x")}


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
    if _int(data, "proposed") > 0 or _int(data, "ask") > 0:
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
    """``plumb ✓ aligned · "add multiply next to add" · SR 12/14 ok (2 by JEV) · 1 awaits
    you``; with ``ascii`` the glyphs become words and ``|`` separators."""
    data = _data(snapshot)
    state = card_state(data)
    total = _int(data, "requirements_total")
    confirmed = _int(data, "requirements_confirmed")
    by = data.get("confirmed_by") if isinstance(data.get("confirmed_by"), Mapping) else {}
    jev = _int(by, "auto-jev")
    parts = [state]
    summary = clip(data.get("intent_summary") or "", SUMMARY_WIDTH)
    if summary:
        parts.append(f'"{summary}"')
    parts.append(f"SR {confirmed}/{total} ok" + (f" ({jev} by JEV)" if jev else ""))
    proposed = _int(data, "proposed")
    if proposed:
        parts.append(f"{proposed} awaits you")
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
    if ascii:
        return to_ascii("plumb | " + " | ".join(parts))
    return f"plumb {GLYPHS[state]} " + " · ".join(parts)


# --------------------------------------------------------------------------- intent card


def _state_text(card: IntentCardData) -> str:
    if card.state == "confirmed":
        by = card.confirmed_by or "you"
        text = f"confirmed by {by}"
        if by == "JEV":
            text += ' — say "revoke" to undo'
    elif card.state == "unconfirmed-edit":
        text = 'changed since you confirmed it — say "ok" to confirm'
    else:
        text = 'proposed — say "ok" to confirm'
    return text + (f", {card.label}" if card.label else "")


def _kind(card: IntentCardData) -> str:
    prefix = card.id.split("-", 1)[0]
    return KINDS.get(prefix, "Record")


def intent_card(card: IntentCardData, *, mode: str = "compact", why: str | None = None,
                ascii: bool = False) -> list[str]:
    """The card's lines (sp5 4.2). ``why`` names a trigger ("Regression", "Question",
    "Intent change") and replaces the kind on line 1. ``mode`` ``off`` renders nothing but
    a trigger card: an interruption the owner must answer is never hidden."""
    if mode == "off" and not why:
        return []
    arrow, dot = (">", "|") if ascii else ("▸", "·")
    lines = [f"{arrow} {why or _kind(card)}  {card.id} \"{card.title}\"   "
             f"({_state_text(card)})"]
    second: list[str] = []
    if card.statement:
        second.append(card.statement)
    elif card.quote:
        second.append(f'You said: "{card.quote}"')
    if card.will:
        second.append("Will: " + "; ".join(card.will))
    if card.wont:
        second.append("Won't: " + "; ".join(card.wont))
    if card.assumed:
        second.append("Assumed: " + "; ".join(card.assumed))
    if card.alternatives:
        second.append("Also fits: " + "; ".join(card.alternatives))
    if second:
        lines.append("  " + f" {dot} ".join(second))
    if card.examples:
        shown = "  ".join(f"{ex} {text}" if sr in (card.id, "") else f"{sr}/{ex} {text}"
                          for sr, ex, text in card.examples)
        lines.append(f"  Examples  {shown}   ({card.state})")
    if card.tests:
        marks = [f"{end}  {TEST_MARKS.get(state, ('', ''))[1 if ascii else 0]} {state}".replace(
            "   ", "  ") for end, state in card.tests]
        lines.append("  Tests  " + "  ".join(marks))
    return [to_ascii(line) for line in lines] if ascii else lines


def cards_text(cards: Sequence[IntentCardData], **kwargs: Any) -> list[str]:
    out: list[str] = []
    for card in cards:
        out.extend(intent_card(card, **kwargs))
    return out
