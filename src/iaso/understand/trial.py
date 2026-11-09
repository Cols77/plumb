"""The trial (JUDGE, SR-106, SR-133, DEC-038).

No trial card is drawn (SR-252 EX-6): a record the judge model finds supported is not put to
the owner and waits for JEV (SR-372). What stays: the calibrated threshold and the owner's
words a record came from. Recalibration reads the logged
scores (``capture.calibrate``) and calls no model."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

NOT_FOUND = "Your words for this were not found."
NO_WORDS = 'The words of yours "{title}" came from are not on file.'


@dataclass(frozen=True)
class Candidate:
    """A supported record waiting for the owner."""

    record: Any
    score: float
    premise: Mapping[str, Any]
    reason: str = ""


# --------------------------------------------------------------------------- thresholds


def claim_kind(record_kind: str) -> str | None:
    from iaso.capture.calibrate import KINDS

    return KINDS.get(record_kind)


def threshold(core: Any, record_kind: str) -> float:
    """The score at which the judge would confirm a ``record_kind`` record: the latest judge
    calibration's threshold for the kind when it passes, else the starting value."""
    from iaso.capture.calibrate import judge_calibrations

    start = float(core.config.understand.reader_threshold_start)
    kind = claim_kind(record_kind)
    for calibration in reversed(judge_calibrations(core)):
        per_kind = calibration.payload.get("per_kind")
        result = per_kind.get(kind) if isinstance(per_kind, Mapping) and kind else None
        if isinstance(result, Mapping):
            if result.get("passing") and result.get("threshold") is not None:
                return float(result["threshold"])
            return start
    return start


def _prompts(core: Any) -> list[dict[str, Any]]:
    out = []
    for line in core.paths.prompt_lines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _prompt_for(prompts: list[dict[str, Any]], digest: str) -> dict[str, Any] | None:
    want = digest.removeprefix("sha256:").strip()
    if not want:
        return None
    for entry in prompts:
        if str(entry.get("digest") or "").removeprefix("sha256:").startswith(want):
            from iaso.hosts.claude_code.prompt import owner_text

            return {"text": owner_text(str(entry.get("text") or "")),
                    "at": str(entry.get("at") or "")}
    return None


def recovered(core: Any, source: Any) -> dict[str, Any] | None:
    """What ``iaso quotes recover`` found for ``source`` in past transcripts (SR-118), or
    None: ``{status, span, at, session, reason, proposed_wording, note}``. Shown, never
    trusted: ``note`` says it was found in a transcript and is not verified."""
    from iaso.understand.recover import finding_for

    try:
        finding = finding_for(core, source)
    except Exception:  # noqa: BLE001 - an unreadable cache shows nothing, it never breaks a card
        return None
    if finding is None:
        return None
    keys = ("status", "span", "at", "session", "reason", "proposed_wording", "note", "by")
    return {key: finding.get(key) for key in keys}


def found_lines(found: Mapping[str, Any] | None) -> list[str]:
    """What a transcript search found (``recovered``) in plain words, or [] when nothing."""
    if not found:
        return []
    from iaso.understand.recover import finding_lines

    return finding_lines(found)


def owner_words(core: Any, record: Any) -> dict[str, Any]:
    """The owner's words ``record`` traces to: for itself when it is an intent, and for each
    intent it derives from, the quote and the logged prompt it came from (where on file).
    ``{"items": [{id, title, quote, prompt, at, found, found_lines}], "note": ""}``; ``note``
    says plainly when none is on file. ``found`` is what a transcript search found
    (``recovered``): shown as found, not verified, it never stands for the owner's logged
    words."""
    index = core.index()
    sources = [record] if record.kind == "intent" else []
    sources += [index[link.target.record] for link in record.links
                if link.kind == "derives_from" and link.target.record in index]
    prompts = _prompts(core) if sources else []
    items = []
    for source in sources:
        raw = source.fields.get("quote") or ""
        parts = raw if isinstance(raw, (list, tuple)) else [raw]   # some intents quote twice
        quote = " / ".join(" ".join(str(p).split()) for p in parts if str(p).strip())
        prompt = _prompt_for(prompts, str(source.fields.get("prompt") or ""))
        found = recovered(core, source)
        if not quote and prompt is None and found is None:
            continue
        items.append({"id": source.id, "title": source.title, "quote": quote or None,
                      "prompt": prompt["text"] if prompt else None,
                      "at": prompt["at"] if prompt else None, "found": found,
                      "found_lines": found_lines(found)})
    return {"items": items, "note": "" if items else NO_WORDS.format(title=record.title)}
