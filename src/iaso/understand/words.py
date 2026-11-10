"""Plain words (JUDGE): ``plain`` puts a record's title where a sentence names a record, so
record numbers, digests and iaso's own words never stand in what the owner reads; ``clip``
shortens a quotation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from iaso.present import owner_text

EVIDENCE_WIDTH = 500

_REF = re.compile(r"(?<![\w-])((?:INT|SR|DEC|FEAT|NC|IC)-\d{3,})"
                  r"(?:(?:\s+|/)(EX|AC|A)-(\d+))?(?![\w-])")
_BARE = re.compile(r"\b(?:EX|AC)-\d+\b")
_DIGEST = re.compile(r"\s*\b(?:sha256:[0-9a-f]+|[0-9a-f]{12,})\b")
_EMPTY = re.compile(r"\s*\(\s*\)")
_ID = re.compile(r"\s*\b(?:clarify|choice|trial|beyond|contradicts|couldnt_check|regression|"
                 r"test_changed|conflict|early_conflict|stale):[\w@.#-]+")


def plain(text: str, index: Mapping[str, Any]) -> str:
    """``text`` as the owner reads it: each record number (and example number) replaced by the
    record's title (and "example n"; a number that names no record is left out of the sentence),
    digests and ids of questions dropped. Callers keep the owner's quoted words out of it."""

    def swap(match: re.Match[str]) -> str:
        record = index.get(match.group(1))
        if record is None:
            return "another record"
        title = f'"{record.title}"'
        if match.group(3):
            n = match.group(3)
            return f"{title} ({owner_text.EXAMPLE_N.format(n=n) if match.group(2) != 'A' else f'assumption {n}'})"
        return title

    text = _EMPTY.sub("", _DIGEST.sub("", _ID.sub("", " ".join(str(text).split()))))
    return _BARE.sub("an example", _REF.sub(swap, text))


def clip(text: str, width: int = EVIDENCE_WIDTH) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."
