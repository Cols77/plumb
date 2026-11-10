"""Small helpers shared by the judgment backends: request fingerprints, a record's text and
the confidence label. (There is no rule-based judge: INT-029.)"""

from __future__ import annotations

from iaso.contracts import Record
from iaso.normalize import canonical_json, sha256_bytes


def fingerprint(*parts: object) -> str:
    return sha256_bytes(canonical_json(list(parts)))


def record_text(record: Record) -> str:
    from iaso.query import record_text as _record_text

    return _record_text(record)


def confidence_label(confidence: float) -> str:
    return "high" if confidence >= 0.9 else ("medium" if confidence >= 0.7 else "low")
