"""Text normalization and hashing primitives (spec 5.4, 12.4).

Extracted and simplified from pi-agent-factory's ``substrate/freshness/fingerprint.py``
(``sha256_bytes``). Standard library only, so hooks can import it cheaply.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

_DERIVED_RE = re.compile(r"<!-- derived -->.*?<!-- end derived -->[ \t]*\n?", re.DOTALL)


def normalize_text(s: str) -> str:
    """CRLF and lone CR to LF, NFC, derived blocks removed, trailing whitespace and blank
    lines dropped (spec 5.4 body rules)."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = unicodedata.normalize("NFC", s)
    s = _DERIVED_RE.sub("", s)
    lines = [line.rstrip() for line in s.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def canonical_json(obj: Any) -> bytes:
    """Sorted keys, compact separators, UTF-8. Non-JSON values (dates) become strings."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    """Hash of the normalized text."""
    return sha256_bytes(normalize_text(s).encode("utf-8"))


def file_digest(path: Path) -> str:
    """Normalized-text hash of a file, or the raw-bytes hash when it is not UTF-8 text."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return sha256_bytes(raw)
    if "\x00" in text:
        return sha256_bytes(raw)
    return sha256_text(text)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
